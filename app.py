#!/usr/bin/env python3
"""
Snake Game - Multi-Mode Edition
Built with PySide6

Modes:
  1. Classic      — Traditional snake with wall death
  2. Speed Frenzy — Speed increases with every food eaten
  3. Maze         — Random wall obstacles spawn on the board
  4. Portal       — Pairs of portals teleport the snake
  5. No-Walls     — Snake wraps around edges; no wall death
"""

import sys
import random
import json
import os
from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QGraphicsDropShadowEffect,
    QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QRadialGradient, QPolygonF, QPainterPath, QPalette
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CELL = 20
COLS = 30
ROWS = 25
BOARD_W = COLS * CELL
BOARD_H = ROWS * CELL

HIGHSCORES_PATH = Path(__file__).parent / "snake_highscores.json"

# ---------------------------------------------------------------------------
# Directions
# ---------------------------------------------------------------------------
class Dir(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    def opposite(self):
        return {
            Dir.UP: Dir.DOWN, Dir.DOWN: Dir.UP,
            Dir.LEFT: Dir.RIGHT, Dir.RIGHT: Dir.LEFT,
        }[self]

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
class Palette:
    BG_DARK = "#1a1a2e"
    BG_MID = "#16213e"
    BG_LIGHT = "#0f3460"
    ACCENT = "#e94560"
    ACCENT2 = "#533483"
    SNAKE_HEAD = "#00d2ff"
    SNAKE_BODY = "#0097a7"
    SNAKE_TAIL = "#004d57"
    FOOD = "#ff6b6b"
    FOOD_GLOW = "#ff000044"
    WALL = "#533483"
    PORTAL_A = "#ff6f00"
    PORTAL_B = "#00e676"
    TEXT = "#ffffff"
    TEXT_DIM = "#8892b0"
    GOLD = "#ffd700"
    GREEN = "#4caf50"
    GRID_LINE = "#ffffff08"

# ---------------------------------------------------------------------------
# Game Mode enum
# ---------------------------------------------------------------------------
class GameMode(Enum):
    CLASSIC = "Classic"
    SPEED = "Speed Frenzy"
    MAZE = "Maze"
    PORTAL = "Portal"
    NOWALLS = "No-Walls"

MODE_DESCRIPTIONS = {
    GameMode.CLASSIC: "Traditional rules. Hit a wall or yourself and it's over.",
    GameMode.SPEED: "The snake accelerates every time it eats! How long can you survive?",
    GameMode.MAZE: "Random obstacles appear on the board. Navigate carefully!",
    GameMode.PORTAL: "Step on a portal and teleport to its twin. Plan your route!",
    GameMode.NOWALLS: "No boundaries — you wrap around to the other side!",
}

MODE_COLORS = {
    GameMode.CLASSIC: "#00d2ff",
    GameMode.SPEED: "#ff6b6b",
    GameMode.MAZE: "#533483",
    GameMode.PORTAL: "#ff6f00",
    GameMode.NOWALLS: "#00e676",
}

# ---------------------------------------------------------------------------
# High-score helper
# ---------------------------------------------------------------------------
def load_highscores():
    if HIGHSCORES_PATH.exists():
        try:
            with open(HIGHSCORES_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {m.value: 0 for m in GameMode}

def save_highscores(scores):
    with open(HIGHSCORES_PATH, "w") as f:
        json.dump(scores, f, indent=2)

# ---------------------------------------------------------------------------
# Snake Game Board Widget
# ---------------------------------------------------------------------------
class GameBoard(QWidget):
    score_changed = Signal(int)
    game_over_signal = Signal(int, object)   # score, mode
    paused_changed = Signal(bool)

    def __init__(self, mode: GameMode, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setFixedSize(BOARD_W, BOARD_H)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Game state
        self.snake = []
        self.direction = Dir.RIGHT
        self.next_direction = Dir.RIGHT
        self.food = (0, 0)
        self.score = 0
        self.is_running = False
        self.is_paused = False
        self.is_game_over = False

        # Mode-specific state
        self.walls = set()
        self.portals = []
        self.base_speed = 120
        self.current_speed = self.base_speed
        self.food_eaten = 0

        # Animation
        self.food_pulse = 0.0
        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self._pulse)
        self.pulse_timer.start(80)

        # Game timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

    # ---- public API ----
    def start_game(self):
        self._reset()
        self.is_running = True
        self.is_game_over = False
        self.is_paused = False
        self.timer.start(self.current_speed)
        self.update()

    def stop_game(self):
        self.timer.stop()
        self.is_running = False

    def toggle_pause(self):
        if not self.is_running or self.is_game_over:
            return
        self.is_paused = not self.is_paused
        self.paused_changed.emit(self.is_paused)
        if self.is_paused:
            self.timer.stop()
        else:
            self.timer.start(self.current_speed)

    # ---- internals ----
    def _reset(self):
        mid_y = ROWS // 2
        self.snake = [(5, mid_y), (4, mid_y), (3, mid_y)]
        self.direction = Dir.RIGHT
        self.next_direction = Dir.RIGHT
        self.score = 0
        self.food_eaten = 0
        self.current_speed = self.base_speed
        self.walls.clear()
        self.portals.clear()
        self.score_changed.emit(0)
        self._spawn_food()

        if self.mode == GameMode.MAZE:
            self._generate_maze()
        elif self.mode == GameMode.PORTAL:
            self._generate_portals()

    def _spawn_food(self):
        occupied = set(self.snake) | self.walls
        for p1, p2 in self.portals:
            occupied.add(p1)
            occupied.add(p2)
        free = [(x, y) for x in range(COLS) for y in range(ROWS) if (x, y) not in occupied]
        if not free:
            self.food = (0, 0)
        else:
            self.food = random.choice(free)

    def _generate_maze(self):
        self.walls.clear()
        num_walls = random.randint(40, 70)
        for _ in range(num_walls):
            x = random.randint(0, COLS - 1)
            y = random.randint(0, ROWS - 1)
            if (x, y) not in self.snake and (x, y) != self.food:
                self.walls.add((x, y))
        # Ensure the starting area is clear
        for sx in range(8):
            for sy in range(ROWS // 2 - 3, ROWS // 2 + 4):
                self.walls.discard((sx, sy))

    def _generate_portals(self):
        self.portals.clear()
        occupied = set(self.snake)
        num_pairs = random.choice([2, 3])
        for _ in range(num_pairs):
            for attempt in range(100):
                a = (random.randint(1, COLS - 2), random.randint(1, ROWS - 2))
                b = (random.randint(1, COLS - 2), random.randint(1, ROWS - 2))
                if a != b and a not in occupied and b not in occupied:
                    if all(abs(a[0] - s[0]) + abs(a[1] - s[1]) > 4 for s in self.snake[:3]) and \
                       all(abs(b[0] - s[0]) + abs(b[1] - s[1]) > 4 for s in self.snake[:3]):
                        self.portals.append((a, b))
                        occupied.add(a)
                        occupied.add(b)
                        break

    def _pulse(self):
        self.food_pulse += 0.15
        if self.food_pulse > 6.28:
            self.food_pulse -= 6.28
        if self.is_running and not self.is_paused:
            self.update()

    def _tick(self):
        if self.is_paused or self.is_game_over or not self.is_running:
            return
        self.direction = self.next_direction
        head_x, head_y = self.snake[0]
        dx, dy = self.direction.value
        new_head = (head_x + dx, head_y + dy)

        # No-Walls wrapping
        if self.mode == GameMode.NOWALLS:
            new_head = (new_head[0] % COLS, new_head[1] % ROWS)

        # Wall collision (all modes except No-Walls)
        if self.mode != GameMode.NOWALLS:
            if not (0 <= new_head[0] < COLS and 0 <= new_head[1] < ROWS):
                self._end_game()
                return

        # Self collision
        if new_head in self.snake[:-1]:
            self._end_game()
            return

        # Maze wall collision
        if new_head in self.walls:
            self._end_game()
            return

        # Portal teleportation
        if self.mode == GameMode.PORTAL:
            for p1, p2 in self.portals:
                if new_head == p1:
                    new_head = p2
                    break
                elif new_head == p2:
                    new_head = p1
                    break

        # Move
        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 10
            self.food_eaten += 1
            self.score_changed.emit(self.score)
            self._spawn_food()

            # Speed Frenzy: get faster
            if self.mode == GameMode.SPEED:
                self.current_speed = max(40, self.base_speed - self.food_eaten * 3)
                self.timer.setInterval(self.current_speed)

            # Maze: add more walls periodically
            if self.mode == GameMode.MAZE and self.food_eaten % 3 == 0:
                self._add_maze_walls(5)
        else:
            self.snake.pop()

        self.update()

    def _add_maze_walls(self, count):
        occupied = set(self.snake) | self.walls | {self.food}
        for _ in range(count):
            for attempt in range(50):
                x = random.randint(0, COLS - 1)
                y = random.randint(0, ROWS - 1)
                if (x, y) not in occupied:
                    self.walls.add((x, y))
                    break

    def _end_game(self):
        self.is_game_over = True
        self.is_running = False
        self.timer.stop()
        self.game_over_signal.emit(self.score, self.mode)
        self.update()

    # ---- keyboard ----
    def keyPressEvent(self, event):
        if not self.is_running or self.is_paused:
            if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_P, Qt.Key.Key_Escape):
                self.toggle_pause()
            elif self.is_running and self.is_paused and event.key() in (
                Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D
            ):
                # Unpause on movement
                self.toggle_pause()
            return

        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key.Key_W) and self.direction != Dir.DOWN:
            self.next_direction = Dir.UP
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_S) and self.direction != Dir.UP:
            self.next_direction = Dir.DOWN
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_A) and self.direction != Dir.RIGHT:
            self.next_direction = Dir.LEFT
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_D) and self.direction != Dir.LEFT:
            self.next_direction = Dir.RIGHT
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_P):
            self.toggle_pause()

    # ---- painting ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_background(p)
        self._draw_grid(p)

        if self.mode == GameMode.MAZE:
            self._draw_walls(p)
        elif self.mode == GameMode.PORTAL:
            self._draw_portals(p)

        self._draw_food(p)
        self._draw_snake(p)

        if self.is_game_over:
            self._draw_game_over(p)
        elif self.is_paused:
            self._draw_paused(p)
        elif not self.is_running and not self.is_game_over:
            self._draw_ready(p)

        p.end()

    def _draw_background(self, p):
        grad = QLinearGradient(0, 0, 0, BOARD_H)
        grad.setColorAt(0, QColor(Palette.BG_DARK))
        grad.setColorAt(1, QColor(Palette.BG_MID))
        p.fillRect(self.rect(), QBrush(grad))

    def _draw_grid(self, p):
        p.setPen(QPen(QColor(Palette.GRID_LINE), 1))
        for x in range(COLS + 1):
            p.drawLine(x * CELL, 0, x * CELL, BOARD_H)
        for y in range(ROWS + 1):
            p.drawLine(0, y * CELL, BOARD_W, y * CELL)

    def _draw_walls(self, p):
        for wx, wy in self.walls:
            rect = QRectF(wx * CELL + 1, wy * CELL + 1, CELL - 2, CELL - 2)
            grad = QRadialGradient(rect.center(), CELL)
            grad.setColorAt(0, QColor("#7c4dff"))
            grad.setColorAt(1, QColor(Palette.WALL))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, 3, 3)

    def _draw_portals(self, p):
        portal_colors = [QColor(Palette.PORTAL_A), QColor(Palette.PORTAL_B),
                         QColor("#e040fb"), QColor("#00bcd4"),
                         QColor("#ffeb3b"), QColor("#ff5722")]
        for idx, (p1, p2) in enumerate(self.portals):
            color = portal_colors[idx % len(portal_colors)]
            self._draw_single_portal(p, p1, color)
            self._draw_single_portal(p, p2, color)

    def _draw_single_portal(self, p, pos, color):
        cx = pos[0] * CELL + CELL / 2
        cy = pos[1] * CELL + CELL / 2
        radius = CELL / 2 - 1
        glow = QRadialGradient(cx, cy, radius + 4)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 80))
        glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), radius + 4, radius + 4)
        inner_r = radius * 0.7 + radius * 0.15 * abs(round(self.food_pulse, 2) % 1)
        p.setBrush(QBrush(color))
        p.setPen(QPen(color.lighter(150), 2))
        p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2, 2)

    def _draw_food(self, p):
        if not self.food:
            return
        fx = self.food[0] * CELL + CELL / 2
        fy = self.food[1] * CELL + CELL / 2
        pulse = 1.0 + 0.18 * abs(round(self.food_pulse, 2) % 1)
        r = (CELL / 2 - 2) * pulse
        glow = QRadialGradient(fx, fy, r + 6)
        glow.setColorAt(0, QColor(Palette.FOOD_GLOW))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(fx, fy), r + 6, r + 6)
        grad = QRadialGradient(fx - r * 0.3, fy - r * 0.3, r)
        grad.setColorAt(0, QColor("#ff9999"))
        grad.setColorAt(1, QColor(Palette.FOOD))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(fx, fy), r, r)

    def _draw_snake(self, p):
        n = len(self.snake)
        for i, (sx, sy) in enumerate(self.snake):
            rect = QRectF(sx * CELL + 1, sy * CELL + 1, CELL - 2, CELL - 2)
            t = i / max(n - 1, 1)
            r = int(0 + t * 0)
            g = int(210 - t * 134)
            b = int(255 - t * 168)
            color = QColor(r, g, b)

            if i == 0:
                grad = QRadialGradient(rect.center(), CELL)
                grad.setColorAt(0, QColor(Palette.SNAKE_HEAD).lighter(130))
                grad.setColorAt(1, QColor(Palette.SNAKE_HEAD))
                p.setBrush(QBrush(grad))
                p.setPen(QPen(QColor("#ffffff"), 1))
                p.drawRoundedRect(rect, 5, 5)
                self._draw_eyes(p, sx, sy)
            else:
                p.setBrush(QBrush(color))
                p.setPen(Qt.PenStyle.NoPen)
                corner = 4 if i < n - 1 else 6
                p.drawRoundedRect(rect, corner, corner)

    def _draw_eyes(self, p, sx, sy):
        cx = sx * CELL + CELL / 2
        cy = sy * CELL + CELL / 2
        dx, dy = self.direction.value
        perp_x, perp_y = -dy, dx
        eye_offset = 3
        fwd_offset = 3
        for sign in (-1, 1):
            ex = cx + dx * fwd_offset + perp_x * eye_offset * sign
            ey = cy + dy * fwd_offset + perp_y * eye_offset * sign
            p.setBrush(QBrush(QColor(255, 255, 255)))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(ex, ey), 2.5, 2.5)
            p.setBrush(QBrush(QColor("#000000")))
            p.drawEllipse(QPointF(ex + dx * 0.8, ey + dy * 0.8), 1.2, 1.2)

    def _draw_overlay_bg(self, p):
        p.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def _draw_game_over(self, p):
        self._draw_overlay_bg(p)
        p.setPen(QPen(QColor(Palette.ACCENT)))
        font = QFont("Segoe UI", 36, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "GAME OVER")

        font2 = QFont("Segoe UI", 18)
        p.setFont(font2)
        p.setPen(QPen(QColor(Palette.TEXT)))
        p.drawText(QRectF(0, BOARD_H / 2 + 20, BOARD_W, 40),
                   Qt.AlignmentFlag.AlignCenter, f"Score: {self.score}")

        font3 = QFont("Segoe UI", 13)
        p.setFont(font3)
        p.setPen(QPen(QColor(Palette.TEXT_DIM)))
        p.drawText(QRectF(0, BOARD_H / 2 + 60, BOARD_W, 30),
                   Qt.AlignmentFlag.AlignCenter, "Press SPACE to return to menu")

    def _draw_paused(self, p):
        self._draw_overlay_bg(p)
        p.setPen(QPen(QColor(Palette.GOLD)))
        font = QFont("Segoe UI", 36, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "PAUSED")

        font2 = QFont("Segoe UI", 14)
        p.setFont(font2)
        p.setPen(QPen(QColor(Palette.TEXT_DIM)))
        p.drawText(QRectF(0, BOARD_H / 2 + 30, BOARD_W, 30),
                   Qt.AlignmentFlag.AlignCenter, "Press SPACE or P to resume")

    def _draw_ready(self, p):
        self._draw_overlay_bg(p)
        mode_color = MODE_COLORS.get(self.mode, Palette.SNAKE_HEAD)
        p.setPen(QPen(QColor(mode_color)))
        font = QFont("Segoe UI", 28, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self.mode.value} Mode")

        font2 = QFont("Segoe UI", 14)
        p.setFont(font2)
        p.setPen(QPen(QColor(Palette.TEXT)))
        p.drawText(QRectF(0, BOARD_H / 2 + 25, BOARD_W, 30),
                   Qt.AlignmentFlag.AlignCenter, "Press any ARROW KEY to start!")


# ---------------------------------------------------------------------------
# Main Menu
# ---------------------------------------------------------------------------
class MainMenu(QWidget):
    mode_selected = Signal(object)

    def __init__(self, highscores, parent=None):
        super().__init__(parent)
        self.highscores = highscores
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Title
        title = QLabel("SNAKE")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 64px;
                font-weight: 900;
                color: {Palette.ACCENT};
                letter-spacing: 12px;
            }}
        """)
        layout.addWidget(title)

        subtitle = QLabel("Multi-Mode Edition")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            QLabel {{
                font-size: 18px;
                color: {Palette.TEXT_DIM};
                letter-spacing: 4px;
                margin-bottom: 20px;
            }}
        """)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Mode buttons
        for mode in GameMode:
            hs = self.highscores.get(mode.value, 0)
            color = MODE_COLORS[mode]
            desc = MODE_DESCRIPTIONS[mode]

            btn = QPushButton(f"  {mode.value}  ")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color}22;
                    border: 2px solid {color}88;
                    border-radius: 10px;
                    padding: 18px 24px;
                    font-size: 20px;
                    font-weight: 700;
                    color: {color};
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {color}44;
                    border-color: {color};
                    border-radius: 10px;
                }}
                QPushButton:pressed {{
                    background-color: {color}66;
                }}
            """)
            btn.setMinimumHeight(60)
            btn.setToolTip(desc)

            row = QFrame()
            row.setStyleSheet("QFrame { background: transparent; border: none; }")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(2)

            btn_row = QHBoxLayout()
            btn_row.addWidget(btn)
            hs_label = QLabel(f"Best: {hs}")
            hs_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            hs_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 16px;
                    color: {Palette.GOLD};
                    font-weight: 600;
                    padding-right: 8px;
                }}
            """)
            btn_row.addWidget(hs_label)
            row_layout.addLayout(btn_row)

            desc_label = QLabel(f"   {desc}")
            desc_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 12px;
                    color: {Palette.TEXT_DIM};
                    padding-left: 10px;
                    padding-bottom: 4px;
                }}
            """)
            row_layout.addWidget(desc_label)

            btn.clicked.connect(lambda checked, m=mode: self.mode_selected.emit(m))
            layout.addWidget(row)

        layout.addSpacing(20)

        footer = QLabel("Arrow Keys / WASD to move  |  SPACE / P to pause")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {Palette.TEXT_DIM};
                letter-spacing: 1px;
            }}
        """)
        layout.addWidget(footer)


# ---------------------------------------------------------------------------
# Game Screen (board + HUD)
# ---------------------------------------------------------------------------
class GameScreen(QWidget):
    back_to_menu = Signal()

    def __init__(self, mode, highscores, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.highscores = highscores
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 15, 20, 15)
        outer.setSpacing(10)

        hud = QHBoxLayout()
        hud.setSpacing(20)

        mode_color = MODE_COLORS.get(self.mode, Palette.SNAKE_HEAD)
        self.mode_label = QLabel(self.mode.value)
        self.mode_label.setStyleSheet(f"""
            QLabel {{
                font-size: 20px;
                font-weight: 800;
                color: {mode_color};
                letter-spacing: 2px;
            }}
        """)

        self.score_label = QLabel("Score: 0")
        self.score_label.setStyleSheet(f"""
            QLabel {{
                font-size: 20px;
                font-weight: 700;
                color: {Palette.TEXT};
            }}
        """)

        self.speed_label = QLabel("")
        self.speed_label.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                color: {Palette.TEXT_DIM};
            }}
        """)

        self.highscore_label = QLabel(f"Best: {self.highscores.get(self.mode.value, 0)}")
        self.highscore_label.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                color: {Palette.GOLD};
                font-weight: 600;
            }}
        """)

        self.back_btn = QPushButton("Menu")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Palette.ACCENT}33;
                border: 1px solid {Palette.ACCENT}88;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 14px;
                font-weight: 600;
                color: {Palette.ACCENT};
            }}
            QPushButton:hover {{
                background-color: {Palette.ACCENT}55;
            }}
        """)
        self.back_btn.clicked.connect(self._on_back)

        hud.addWidget(self.mode_label)
        hud.addStretch()
        hud.addWidget(self.speed_label)
        hud.addWidget(self.score_label)
        hud.addWidget(self.highscore_label)
        hud.addWidget(self.back_btn)

        outer.addLayout(hud)

        board_frame = QFrame()
        board_frame.setStyleSheet(f"""
            QFrame {{
                background: {Palette.BG_DARK};
                border: 2px solid {mode_color}44;
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        board_layout = QVBoxLayout(board_frame)
        board_layout.setContentsMargins(4, 4, 4, 4)
        board_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.board = GameBoard(self.mode)
        board_layout.addWidget(self.board, alignment=Qt.AlignmentFlag.AlignCenter)

        outer.addWidget(board_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("Arrow Keys / WASD to move  |  SPACE / P to pause")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {Palette.TEXT_DIM};
            }}
        """)
        outer.addWidget(hint)

        self.board.score_changed.connect(self._on_score_changed)
        self.board.game_over_signal.connect(self._on_game_over)
        self.board.paused_changed.connect(self._on_paused)

    def _on_score_changed(self, score):
        self.score_label.setText(f"Score: {score}")
        if self.mode == GameMode.SPEED:
            speed_pct = int((1 - (self.board.current_speed - 40) / (self.board.base_speed - 40)) * 100)
            self.speed_label.setText(f"Speed: +{speed_pct}%")

    def _on_game_over(self, score, mode):
        key = mode.value
        if score > self.highscores.get(key, 0):
            self.highscores[key] = score
            self.highscore_label.setText(f"Best: {score}")
            save_highscores(self.highscores)

    def _on_paused(self, paused):
        pass

    def _on_back(self):
        self.board.stop_game()
        self.back_to_menu.emit()

    def activate(self):
        self.board.setFocus()
        self.board.start_game()

    def deactivate(self):
        self.board.stop_game()


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.highscores = load_highscores()
        self._build_ui()
        self._apply_global_style()
        self._show_menu()

    def _build_ui(self):
        self.setWindowTitle("Snake - Multi-Mode Edition")
        self.setMinimumSize(700, 680)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

    def _apply_global_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {Palette.BG_DARK};
            }}
            QWidget {{
                background-color: transparent;
            }}
        """)

    def _show_menu(self):
        current = self.stack.currentWidget()
        if isinstance(current, GameScreen):
            current.deactivate()

        menu = MainMenu(self.highscores)
        menu.mode_selected.connect(self._on_mode_selected)
        self.stack.addWidget(menu)
        self.stack.setCurrentWidget(menu)
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

    def _on_mode_selected(self, mode):
        game = GameScreen(mode, self.highscores)
        game.back_to_menu.connect(self._show_menu)
        self.stack.addWidget(game)
        self.stack.setCurrentWidget(game)
        self.adjustSize()
        screen = self.screen().availableGeometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )
        game.activate()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(Palette.BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(Palette.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(Palette.BG_MID))
    palette.setColor(QPalette.ColorRole.Text, QColor(Palette.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(Palette.BG_LIGHT))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(Palette.TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(Palette.ACCENT))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()