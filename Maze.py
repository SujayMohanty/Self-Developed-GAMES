"""
maze_dungeon_hint_ui_patched_v4.py
- HUD word-wrap + vertical scrollbar (mouse wheel & draggable thumb)
- Keeps minimap visible when HUD minimized and draggable
- All prior features retained
"""

import pygame
import random
import time
import math
import tempfile
import wave
import struct
import os
import json

# ---------- Config ----------
FPS = 60
BASE_TILE = 24
HUD_WIDTH = 300
MARGIN = 8
WINDOW_BG = (18, 18, 22)

# Visibility
BASE_REVEAL_RADIUS = 3
GLOW_DURATION = 0.7  # seconds glow remains visible after movement (transient)

# Pinger / hint
PINGER_SHOW_SEC = 2.0  # arrow visible for this many seconds when clicked

# Sound / audio
SAMPLE_RATE = 44100
MAX_AMPLITUDE = 32767
AMBIENT_LENGTH = 8.0
_temp_sound_files = []

# Colors (default and minimap)
COLOR_WALL = (40, 40, 50)
COLOR_FLOOR = (200, 190, 170)  # fallback, but per-level colors will be used
COLOR_PLAYER = (80, 200, 120)
COLOR_HIDDEN = (6, 6, 10)
COLOR_TEXT = (230, 230, 230)
COLOR_HUD_BG = (14, 14, 18)
COLOR_STATS = (200, 200, 220)
COLOR_MINIMAP_WALL = (40, 40, 50)
COLOR_MINIMAP_FLOOR_VISIBLE = (90, 90, 70)
COLOR_MINIMAP_FLOOR_HIDDEN = (18, 18, 22)
COLOR_MINIMAP_PLAYER = (120, 220, 140)
COLOR_HINT_FLASH = (220, 20, 20)
COLOR_PINGER_ARROW = (220, 40, 40, 240)  # RGBA for arrow surface
COLOR_BUTTON = (36,36,40)
COLOR_BUTTON_TEXT = (220,220,220)
COLOR_RECORD_HIGHLIGHT = (255, 220, 120)
COLOR_SCROLL_TRACK = (28,28,32)
COLOR_SCROLL_THUMB = (96,96,96)

# Floor palette per level (1..10)
LEVEL_FLOOR_COLORS = {
    1:  (200, 190, 170),
    2:  (185, 170, 150),
    3:  (160, 200, 180),
    4:  (200, 160, 200),
    5:  (220, 200, 140),
    6:  (140, 180, 220),
    7:  (200, 120, 100),
    8:  (120, 200, 160),
    9:  (180, 140, 200),
    10: (210, 210, 150),
}

# record file path (per-user)
RECORD_FILE = os.path.join(os.path.expanduser("~"), ".maze_dungeon_records.json")

MOVE_KEYS = {
    pygame.K_w: (0, -1), pygame.K_UP: (0, -1),
    pygame.K_s: (0, 1),  pygame.K_DOWN: (0, 1),
    pygame.K_a: (-1, 0), pygame.K_LEFT: (-1, 0),
    pygame.K_d: (1, 0),  pygame.K_RIGHT: (1, 0),
}

# Level sizes
LEVEL_MAP = {
    1: (31, 21),
    2: (41, 27),
    3: (55, 35),
    4: (65, 45),
    5: (75, 50),
    6: (85, 54),
    7: (95, 56),
    8: (100, 58),
    9: (105, 60),
    10: (110, 62),
}

# ---------- audio helpers (same as before, kept minimal) ----------
def clamp(v, a, b):
    return max(a, min(b, v))

def generate_sine_wave(freq, duration, vol=0.3, sr=SAMPLE_RATE):
    total = int(duration * sr)
    return [math.sin(2*math.pi*freq*(i/sr)) * vol for i in range(total)]

def generate_noise(duration, vol=0.2, sr=SAMPLE_RATE):
    total = int(duration * sr)
    return [random.uniform(-1.0, 1.0)*vol for _ in range(total)]

def mix_signals(signals):
    length = max((len(s) for s in signals), default=0)
    out = [0.0]*length
    for s in signals:
        for i, v in enumerate(s):
            out[i] += v
    maxv = max((abs(x) for x in out), default=1.0)
    if maxv > 1.0:
        out = [x/maxv for x in out]
    return out

def write_wav(samples, path, sr=SAMPLE_RATE):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = b"".join(struct.pack("<h", int(clamp(s, -1.0, 1.0)*MAX_AMPLITUDE)) for s in samples)
        wf.writeframes(frames)

def make_temp_wav(samples):
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    write_wav(samples, path)
    _temp_sound_files.append(path)
    return path

def make_ambient(tier):
    dur = AMBIENT_LENGTH
    if tier == 1:
        s1 = generate_sine_wave(60, dur, 0.18)
        s2 = generate_sine_wave(140, dur, 0.06)
        n = generate_noise(dur, 0.02)
        sig = mix_signals([s1, s2, n])
    elif tier == 2:
        s1 = generate_sine_wave(45, dur, 0.22)
        s2 = generate_sine_wave(110, dur, 0.08)
        n = generate_noise(dur, 0.03)
        mod = [0.9 + 0.1*math.sin(2*math.pi*0.18*(i/SAMPLE_RATE)) for i in range(int(dur*SAMPLE_RATE))]
        raw = mix_signals([s1, s2, n])
        sig = [raw[i]*mod[i] for i in range(len(raw))]
    else:
        s1 = generate_sine_wave(32, dur, 0.28)
        s2 = generate_sine_wave(90, dur, 0.09)
        n = generate_noise(dur, 0.06)
        mod = [0.85 + 0.15*math.sin(2*math.pi*0.35*(i/SAMPLE_RATE)) for i in range(int(dur*SAMPLE_RATE))]
        raw = mix_signals([s1, s2, n])
        sig = [raw[i]*mod[i] for i in range(len(raw))]
    return make_temp_wav(sig)

def make_exit_sfx(tier):
    if tier == 1:
        a = generate_sine_wave(200, 0.15, vol=0.6)
        b = generate_sine_wave(320, 0.6, vol=0.22)
        n = generate_noise(0.9, 0.05)
        core = mix_signals([a + [0]*int(0.45*SAMPLE_RATE), b, n])
        atten = [math.exp(-3.0*(i/SAMPLE_RATE)) for i in range(len(core))]
        out = [core[i]*atten[i] for i in range(len(core))]
    elif tier == 2:
        a = generate_sine_wave(220, 0.45, vol=0.6)
        b = generate_sine_wave(440, 0.7, vol=0.25)
        n = generate_noise(0.9, 0.06)
        core = mix_signals([a + [0]*int(0.45*SAMPLE_RATE), b + [0]*int(0.2*SAMPLE_RATE), n])
        atten = [math.exp(-3.0*(i/SAMPLE_RATE)) for i in range(len(core))]
        out = [core[i]*atten[i] for i in range(len(core))]
    else:
        t = 1.6
        s1 = generate_sine_wave(120, t, vol=0.9)
        s2 = generate_sine_wave(60, t, vol=0.6)
        n = generate_noise(t, vol=0.35)
        total = int(t*SAMPLE_RATE)
        env = [(1.0 if (i/total) < 0.02 else math.exp(-6.0*((i/total)))) for i in range(total)]
        base = mix_signals([s1, s2, n])
        out = [base[i]*env[i] for i in range(len(base))]
    return make_temp_wav(out)

def make_hint_sfx(tier):
    if tier == 1:
        s1 = generate_sine_wave(660, 0.12, 0.35)
        s2 = generate_sine_wave(880, 0.18, 0.18)
        sig = mix_signals([s1, s2])
    elif tier == 2:
        s1 = generate_sine_wave(440, 0.14, 0.45)
        s2 = generate_sine_wave(660, 0.16, 0.2)
        n = generate_noise(0.3, 0.02)
        sig = mix_signals([s1, s2, n])
    else:
        s1 = generate_sine_wave(220, 0.25, 0.55)
        n = generate_noise(0.6, 0.06)
        sig = mix_signals([s1, n])
    return make_temp_wav(sig)

def cleanup_temp_sounds():
    for p in _temp_sound_files:
        try:
            os.remove(p)
        except:
            pass

# ---------- maze generation ----------
def generate_maze(width, height, seed=None):
    if seed is not None:
        random.seed(seed)
    gw = width if width%2==1 else width+1
    gh = height if height%2==1 else height+1
    grid = [[1 for _ in range(gw)] for _ in range(gh)]
    sx, sy = 1, 1
    grid[sy][sx] = 0
    stack = [(sx, sy)]
    dirs = [(2,0),(-2,0),(0,2),(0,-2)]
    while stack:
        x, y = stack[-1]
        neighbors = []
        for dx, dy in dirs:
            nx, ny = x+dx, y+dy
            if 1 <= nx < gw-1 and 1 <= ny < gh-1 and grid[ny][nx] == 1:
                neighbors.append((nx, ny, dx, dy))
        if neighbors:
            nx, ny, dx, dy = random.choice(neighbors)
            wx, wy = x + dx//2, y + dy//2
            grid[wy][wx] = 0
            grid[ny][nx] = 0
            stack.append((nx, ny))
        else:
            stack.pop()
    return grid

def find_open_positions(grid):
    pos = []
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v == 0:
                pos.append((x,y))
    return pos

def manhattan(a,b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])

# ---------- game ----------
class MazeGame:
    def __init__(self, level=1, fixed_seed=None):
        pygame.init()
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE)
        except:
            print("Audio disabled")
        self.level = max(1, min(10, level))
        self.fixed_seed = fixed_seed
        self.moves = 0
        self.start_time = time.time()

        self.ambient_channel = pygame.mixer.Channel(1) if pygame.mixer.get_init() else None
        self.sfx_channel = pygame.mixer.Channel(2) if pygame.mixer.get_init() else None

        self.fullscreen = False
        self.flags = pygame.RESIZABLE | pygame.DOUBLEBUF

        # visibility
        self.seen = set()           # kept but not used in movement-only mode
        self.visible_ts = {}

        # hint/pinger variables
        self.pinger_active_until = 0.0
        self.hint_count = 0

        self.hint_sfx_path = None
        self.exit_sfx_path = None

        # debug
        self.debug_show_exit = False

        # HUD minimized?
        self.hud_minimized = False

        # rectangles for clickable buttons (populated in draw)
        self.hint_button_rect = None
        self.minimize_button_rect = None

        # HUD scroll state
        self.hud_scroll = 0.0
        self.hud_dragging_scroll = False
        self.hud_scroll_drag_offset = 0.0

        # minimap floating state (position & size). Will be set on first draw if None.
        self.mini_w = 220
        self.mini_h = 140
        self.mini_pos = None  # (x,y)
        self.dragging_minimap = False
        self.drag_offset = (0,0)

        # records (load persisted best times)
        self.records = self.load_records()

        self.generate_for_level(self.level)

        self.base_tile = BASE_TILE
        self.win_w = min(1400, self.grid_w * self.base_tile + HUD_WIDTH + MARGIN*3)
        self.win_h = min(900, max(self.grid_h * self.base_tile + MARGIN*2, 480))
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), self.flags)
        pygame.display.set_caption(f"Maze Dungeon — Level {self.level}")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Consolas", 16)
        self.bigfont = pygame.font.SysFont("Consolas", 20, bold=True)
        self.smallfont = pygame.font.SysFont("Consolas", 14)
        self.running = True

        self.update_render_metrics()
        self.start_ambient()

    # ---------- records persistence ----------
    def load_records(self):
        try:
            if os.path.exists(RECORD_FILE):
                with open(RECORD_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            print("Failed to load records:", e)
        return {}  # { "1": seconds_float, ... }

    def save_records(self):
        try:
            with open(RECORD_FILE, "w") as f:
                json.dump(self.records, f)
        except Exception as e:
            print("Failed to save records:", e)

    # ---------- floor color helper ----------
    def get_floor_color(self, level):
        return LEVEL_FLOOR_COLORS.get(level, COLOR_FLOOR)

    # ---------- text wrapping helpers ----------
    def wrap_text_to_lines(self, text, font, max_width):
        # returns list of lines (strings)
        words = text.split()
        if not words:
            return []
        lines = []
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            if font.size(test)[0] <= max_width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    def generate_hud_lines(self, x_text, pad):
        # Compose HUD paragraphs into a list of wrapped lines with prefixes where needed.
        max_w = HUD_WIDTH - pad*2 - 12  # leave room for scrollbar
        lines = []
        # Title (single line)
        lines.append(("MAZE DUNGEON", self.bigfont, COLOR_TEXT))
        lines.append(("", self.font, COLOR_TEXT))  # spacer

        # Basic stats - these are dynamic; we'll place placeholders and render with format later
        elapsed = int(time.time() - self.start_time)
        stats = [
            (f"Level: {self.level} / 10", self.font, COLOR_STATS),
            (f"Time: {elapsed}s", self.font, COLOR_STATS),
            (f"Moves: {self.moves}", self.font, COLOR_STATS),
            (f"Reveal radius: {self.reveal_radius} tiles", self.font, COLOR_STATS),
            (f"Seed: {self.seed_used}", self.font, COLOR_STATS),
            ("", self.font, COLOR_TEXT),
        ]
        for item in stats:
            lines.append(item)

        # OBJECTIVE
        lines.append(("OBJECTIVE:", self.font, COLOR_TEXT))
        obj_lines = self.wrap_text_to_lines("Step on the invisible EXIT tile to advance to the next level.", self.font, max_w)
        for l in obj_lines:
            lines.append((l, self.font, COLOR_STATS))
        lines.append(("", self.font, COLOR_TEXT))

        # EXIT HINTS
        lines.append(("EXIT HINTS:", self.font, COLOR_TEXT))
        eh1 = self.wrap_text_to_lines("- Click HINT to show an arrow toward the exit.", self.font, max_w)
        for l in eh1: lines.append((l, self.font, COLOR_STATS))
        eh2 = self.wrap_text_to_lines(f"- Arrow visible for {PINGER_SHOW_SEC:.0f} seconds. Hints counted above.", self.font, max_w)
        for l in eh2: lines.append((l, self.font, COLOR_STATS))
        lines.append(("", self.font, COLOR_TEXT))

        # VISIBILITY
        lines.append(("VISIBILITY:", self.font, COLOR_TEXT))
        v1 = self.wrap_text_to_lines("- Tiles glow when you move nearby.", self.font, max_w)
        for l in v1: lines.append((l, self.font, COLOR_STATS))
        lines.append(("", self.font, COLOR_TEXT))
        v2 = self.wrap_text_to_lines("- The MiniMap can be toggled and moved after minimization for better gameplay.", self.font, max_w)
        for l in v2: lines.append((l, self.font, COLOR_STATS))
        lines.append(("", self.font, COLOR_TEXT))

        # CONTROLS
        lines.append(("CONTROLS:", self.font, COLOR_TEXT))
        ctrl_texts = [
            "W/A/S/D or Arrows - Move",
            "H - Hint",
            "M - Toggle HUD",
            "R - Regenerate level",
            "N - Next level (skip/test)",
            "F11 - Fullscreen",
            "D - Debug: reveal exit",
            "Q / ESC - Quit",
        ]
        for t in ctrl_texts:
            wrapped = self.wrap_text_to_lines(t, self.font, max_w)
            for l in wrapped:
                lines.append((l, self.font, COLOR_STATS))
        lines.append(("", self.font, COLOR_TEXT))

        return lines

    def generate_for_level(self, level):
        self.level = max(1, min(10, level))
        w, h = LEVEL_MAP.get(self.level, (33,21))
        seed = self.fixed_seed if self.fixed_seed is not None else random.randint(0, 2**30)
        self.seed_used = seed
        base_grid = generate_maze(w, h, seed=seed)

        grid = [row[:] for row in base_grid]
        if self.level >= 3:
            extra_wall_chance = 0.04 + (self.level - 3) * 0.015
            opens = find_open_positions(grid)
            random.shuffle(opens)
            attempts = int(len(opens) * extra_wall_chance)
            for i in range(attempts):
                x,y = opens[i]
                if (x,y) == (1,1): continue
                nopen = sum(1 for dx,dy in [(1,0),(-1,0),(0,1),(0,-1)]
                            if 0 <= x+dx < len(grid[0]) and 0 <= y+dy < len(grid) and grid[y+dy][x+dx] == 0)
                if nopen >= 2 and random.random() < extra_wall_chance:
                    grid[y][x] = 1

        self.grid = grid
        self.grid_w = len(grid[0])
        self.grid_h = len(grid)
        opens = find_open_positions(grid)
        self.player_pos = min(opens, key=lambda p: p[0] + p[1])
        self.exit_pos = max(opens, key=lambda p: manhattan(p, self.player_pos))

        if self.level == 1:
            self.reveal_radius = BASE_REVEAL_RADIUS + 1
        else:
            self.reveal_radius = max(2, BASE_REVEAL_RADIUS - 1)

        # floor color for this level
        self.floor_color = self.get_floor_color(self.level)

        self.seen.clear()
        self.visible_ts.clear()
        self.register_current_visibility(initial=True)

        self.moves = 0
        self.start_time = time.time()
        self.hint_count = 0
        self.pinger_active_until = 0.0
        self.hint_last_time = None

        self.start_ambient()

    def register_current_visibility(self, initial=False):
        px, py = self.player_pos
        now = time.time()
        r = self.reveal_radius
        xmin = max(0, px - r)
        xmax = min(self.grid_w - 1, px + r)
        ymin = max(0, py - r)
        ymax = min(self.grid_h - 1, py + r)
        for y in range(ymin, ymax + 1):
            for x in range(xmin, xmax + 1):
                if self.grid[y][x] == 0 and manhattan((x, y), (px, py)) <= r:
                    self.visible_ts[(x, y)] = now

    def start_ambient(self):
        try:
            if self.ambient_channel:
                self.ambient_channel.stop()
        except:
            pass
        tier = 1 if self.level <= 2 else 2 if self.level <= 6 else 3
        try:
            amb_path = make_ambient(tier)
            if pygame.mixer.get_init():
                sound = pygame.mixer.Sound(amb_path)
                vol = 0.22 if tier == 1 else 0.26 if tier == 2 else 0.36
                self.ambient_channel.set_volume(vol)
                self.ambient_channel.play(sound, loops=-1)
        except Exception as e:
            print("Ambient start fail:", e)
        try:
            s_tier = 1 if self.level <= 2 else 2 if self.level <= 6 else 3
            self.exit_sfx_path = make_exit_sfx(s_tier)
            self.hint_sfx_path = make_hint_sfx(s_tier)
        except Exception as e:
            print("SFX gen fail:", e)
            self.exit_sfx_path = None
            self.hint_sfx_path = None

    def update_render_metrics(self):
        w, h = self.screen.get_size()
        maze_w_space = w - HUD_WIDTH - MARGIN*4
        maze_h_space = h - MARGIN*2
        if self.grid_w and self.grid_h:
            scale_x = maze_w_space / (self.grid_w * self.base_tile)
            scale_y = maze_h_space / (self.grid_h * self.base_tile)
            scale = min(scale_x, scale_y, 2.0)
            self.draw_tile = max(6, int(round(self.base_tile * scale)))
        else:
            self.draw_tile = self.base_tile
        self.maze_surface_w = self.grid_w * self.draw_tile
        self.maze_surface_h = self.grid_h * self.draw_tile
        self.maze_surface = pygame.Surface((self.maze_surface_w, self.maze_surface_h))

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return
            # KEYDOWN
            if event.type == pygame.KEYDOWN:
                if event.key in MOVE_KEYS:
                    dx, dy = MOVE_KEYS[event.key]
                    self.try_move(dx, dy)
                elif event.key == pygame.K_r:
                    self.fixed_seed = None
                    self.generate_for_level(self.level)
                elif event.key == pygame.K_n:
                    self.level = min(10, self.level+1)
                    self.generate_for_level(self.level)
                elif event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif event.key == pygame.K_d:
                    self.debug_show_exit = not self.debug_show_exit
                elif event.key == pygame.K_h:
                    # keyboard hint
                    self.trigger_hint()
                elif event.key == pygame.K_m:
                    # toggle HUD fully hidden / restore
                    self.hud_minimized = not self.hud_minimized
            # Mouse down
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                # HUD scrollbar dragging (only if HUD visible)
                left_x = MARGIN
                left_y = MARGIN
                hud_x = left_x + self.maze_surface_w + MARGIN
                hud_rect = pygame.Rect(hud_x, MARGIN, HUD_WIDTH, self.win_h - MARGIN*2)
                if not self.hud_minimized:
                    # compute scrollbar rect for hit test
                    pad = 12
                    view_h = hud_rect.height - pad*2 - 40  # approx area used for content
                    scroll_x = hud_rect.right - 12
                    track_rect = pygame.Rect(scroll_x, hud_rect.y + pad + 8, 8, view_h)
                    # compute content lines to get thumb pos
                    lines = self.generate_hud_lines(hud_x + pad, pad)
                    line_height = self.font.get_linesize()
                    content_h = sum(font.get_linesize() if font != self.bigfont else self.bigfont.get_linesize() for (_, font, _) in lines)
                    max_scroll = max(0, content_h - view_h)
                    if content_h > 0 and max_scroll > 0:
                        thumb_h = max(20, int(view_h * (view_h / content_h)))
                        thumb_y = track_rect.y
                        if max_scroll > 0:
                            thumb_y = track_rect.y + int((self.hud_scroll / max_scroll) * (track_rect.height - thumb_h))
                        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_h)
                        if thumb_rect.collidepoint(mx, my):
                            self.hud_dragging_scroll = True
                            self.hud_scroll_drag_offset = my - thumb_y
                            continue
                # minimap dragging when HUD minimized
                if self.hud_minimized:
                    if self.mini_pos is not None:
                        mini_x, mini_y = self.mini_pos
                        mini_rect = pygame.Rect(mini_x, mini_y, self.mini_w, self.mini_h)
                        if mini_rect.collidepoint(mx, my):
                            self.dragging_minimap = True
                            self.drag_offset = (mx - mini_x, my - mini_y)
                            continue
                # otherwise check HUD buttons (only when HUD visible)
                if getattr(self, "hint_button_rect", None) and self.hint_button_rect.collidepoint(mx, my):
                    self.trigger_hint()
                if getattr(self, "minimize_button_rect", None) and self.minimize_button_rect.collidepoint(mx, my):
                    self.hud_minimized = not self.hud_minimized
            # Mouse up
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging_minimap:
                    self.dragging_minimap = False
                if self.hud_dragging_scroll:
                    self.hud_dragging_scroll = False
            # Mouse motion (dragging)
            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                if self.dragging_minimap:
                    ox, oy = self.drag_offset
                    new_x = mx - ox
                    new_y = my - oy
                    # clamp so the minimap stays inside the maze drawing area
                    left_x = MARGIN
                    left_y = MARGIN
                    min_x = left_x
                    min_y = left_y
                    max_x = left_x + max(0, self.maze_surface_w - self.mini_w)
                    max_y = left_y + max(0, self.maze_surface_h - self.mini_h)
                    new_x = int(clamp(new_x, min_x, max_x))
                    new_y = int(clamp(new_y, min_y, max_y))
                    self.mini_pos = (new_x, new_y)
                if self.hud_dragging_scroll:
                    # compute new hud_scroll based on mouse y
                    left_x = MARGIN
                    hud_x = left_x + self.maze_surface_w + MARGIN
                    hud_rect = pygame.Rect(hud_x, MARGIN, HUD_WIDTH, self.win_h - MARGIN*2)
                    pad = 12
                    view_h = hud_rect.height - pad*2 - 40
                    track_y = hud_rect.y + pad + 8
                    track_h = view_h
                    lines = self.generate_hud_lines(hud_x + pad, pad)
                    content_h = sum(font.get_linesize() if font != self.bigfont else self.bigfont.get_linesize() for (_, font, _) in lines)
                    max_scroll = max(0, content_h - view_h)
                    thumb_h = max(20, int(view_h * (view_h / content_h))) if content_h>0 else view_h
                    # compute relative position
                    rel = my - track_y - (self.hud_scroll_drag_offset - thumb_h//2)
                    # clamp rel
                    rel = clamp(rel, 0, max(0, track_h - thumb_h))
                    if max_scroll > 0:
                        self.hud_scroll = (rel / max(0, track_h - thumb_h)) * max_scroll
                    else:
                        self.hud_scroll = 0.0
            # Mouse wheel (modern pygame)
            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                left_x = MARGIN
                hud_x = left_x + self.maze_surface_w + MARGIN
                hud_rect = pygame.Rect(hud_x, MARGIN, HUD_WIDTH, self.win_h - MARGIN*2)
                # if HUD visible and mouse over HUD, scroll; if HUD hidden and mouse over minimap, ignore
                if not self.hud_minimized and hud_rect.collidepoint(mx, my):
                    # event.y is typically +1 for up, -1 for down
                    self.hud_scroll -= event.y * 24
                    # clamp after updating
                    pad = 12
                    view_h = hud_rect.height - pad*2 - 40
                    lines = self.generate_hud_lines(hud_x + pad, pad)
                    content_h = sum(font.get_linesize() if font != self.bigfont else self.bigfont.get_linesize() for (_, font, _) in lines)
                    max_scroll = max(0, content_h - view_h)
                    self.hud_scroll = clamp(self.hud_scroll, 0, max_scroll)
            elif event.type == pygame.VIDEORESIZE:
                self.win_w, self.win_h = event.w, event.h
                self.screen = pygame.display.set_mode((self.win_w, self.win_h), self.flags)
                self.update_render_metrics()

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        else:
            self.screen = pygame.display.set_mode((self.win_w, self.win_h), self.flags)
        self.update_render_metrics()

    def try_move(self, dx, dy):
        nx = self.player_pos[0] + dx
        ny = self.player_pos[1] + dy
        if 0 <= nx < self.grid_w and 0 <= ny < self.grid_h and self.grid[ny][nx] == 0:
            self.player_pos = (nx, ny)
            self.moves += 1
            self.perform_move_visibility()
            if self.player_pos == self.exit_pos:
                try:
                    if self.exit_sfx_path and pygame.mixer.get_init():
                        sfx = pygame.mixer.Sound(self.exit_sfx_path)
                        vol = 0.7 if self.level <= 2 else 0.9 if self.level <= 6 else 1.0
                        self.sfx_channel.set_volume(vol)
                        self.sfx_channel.play(sfx)
                except Exception as e:
                    print("Exit sfx fail:", e)
                self.on_exit_found()

    def perform_move_visibility(self):
        px, py = self.player_pos
        now = time.time()
        r = self.reveal_radius
        xmin = max(0, px - r)
        xmax = min(self.grid_w - 1, px + r)
        ymin = max(0, py - r)
        ymax = min(self.grid_h - 1, py + r)
        for y in range(ymin, ymax + 1):
            for x in range(xmin, xmax + 1):
                if self.grid[y][x] == 0 and manhattan((x, y), (px, py)) <= r:
                    self.visible_ts[(x, y)] = now

    def is_visible(self, tx, ty):
        now = time.time()
        if (tx, ty) == self.player_pos:
            return True
        ts = self.visible_ts.get((tx, ty))
        if ts is not None and (now - ts) <= GLOW_DURATION:
            return True
        return False

    def trigger_hint(self):
        now = time.time()
        self.pinger_active_until = now + PINGER_SHOW_SEC
        self.hint_count += 1
        try:
            if self.hint_sfx_path and pygame.mixer.get_init():
                sfx = pygame.mixer.Sound(self.hint_sfx_path)
                vol = 0.26 if self.level <= 2 else 0.5 if self.level <= 6 else 0.8
                self.sfx_channel.set_volume(vol)
                self.sfx_channel.play(sfx)
        except Exception as e:
            print("Hint play fail:", e)

    def on_exit_found(self):
        now = time.time()
        level_elapsed = now - self.start_time
        hints_used = self.hint_count
        lvl_key = str(self.level)
        prev_best = self.records.get(lvl_key, None)
        new_record = False
        if prev_best is None or level_elapsed < prev_best:
            self.records[lvl_key] = level_elapsed
            self.save_records()
            new_record = True

        overlay_start = time.time()
        overlay_duration = 3.0
        while time.time() - overlay_start < overlay_duration:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.running = False
                    return
            self.draw()
            overlay_w = 420
            overlay_h = 140
            ox = (self.win_w - overlay_w) // 2
            oy = (self.win_h - overlay_h) // 2
            s = pygame.Surface((overlay_w, overlay_h), pygame.SRCALPHA)
            s.fill((8, 8, 10, 220))
            title = f"Level {self.level} cleared!"
            line1 = f"Hints used: {hints_used}"
            line2 = f"Time: {int(level_elapsed)}s"
            if prev_best is None:
                prev_display = "—"
            else:
                prev_display = f"{int(prev_best)}s"
            if new_record:
                note = f"New personal best! ({int(level_elapsed)}s)"
            else:
                note = f"Personal fastest: {prev_display}"
            self.screen.blit(s, (ox, oy))
            self.draw_text(title, ox + 18, oy + 12, self.bigfont, COLOR_TEXT)
            self.draw_text(line1, ox + 18, oy + 44, self.font, COLOR_STATS)
            self.draw_text(line2, ox + 18, oy + 64, self.font, COLOR_STATS)
            if new_record:
                self.draw_text(note, ox + 18, oy + 88, self.font, COLOR_RECORD_HIGHLIGHT)
            else:
                self.draw_text(note, ox + 18, oy + 88, self.font, COLOR_STATS)
            pygame.display.flip()
            self.clock.tick(30)

        self.level = min(10, self.level + 1)
        self.generate_for_level(self.level)
        pygame.display.set_caption(f"Maze Dungeon — Level {self.level}")

    def draw_pinger_arrow(self, surface, center_x, center_y, angle_rad, size_px, alpha=255):
        surf = pygame.Surface((size_px*2, size_px*2), pygame.SRCALPHA)
        cx = size_px
        cy = size_px
        pts = [
            (cx + size_px, cy),
            (cx - int(size_px*0.6), cy - int(size_px*0.6)),
            (cx - int(size_px*0.6), cy + int(size_px*0.6)),
        ]
        col = COLOR_PINGER_ARROW[:3] + (clamp(alpha, 0, 255),)
        pygame.draw.polygon(surf, col, pts)
        rotated = pygame.transform.rotate(surf, -math.degrees(angle_rad))
        rrect = rotated.get_rect(center=(center_x, center_y - int(self.draw_tile * 0.9)))
        surface.blit(rotated, rrect.topleft)

    def draw_minimap_at(self, mini_x, mini_y, mini_w, mini_h, px, py, pinger_remaining):
        """Helper: draw minimap at given coords onto self.screen"""
        mini_rect = pygame.Rect(mini_x, mini_y, mini_w, mini_h)
        pygame.draw.rect(self.screen, (12,12,15), mini_rect, border_radius=6)
        if self.grid_w and self.grid_h:
            cell_w = mini_w / self.grid_w
            cell_h = mini_h / self.grid_h
            scale = min(cell_w, cell_h)
            offset_x = mini_x + (mini_w - scale * self.grid_w) / 2
            offset_y = mini_y + (mini_h - scale * self.grid_h) / 2
            for y in range(self.grid_h):
                for x in range(self.grid_w):
                    color = COLOR_MINIMAP_WALL if self.grid[y][x] == 1 else (COLOR_MINIMAP_FLOOR_VISIBLE if self.is_visible(x,y) else COLOR_MINIMAP_FLOOR_HIDDEN)
                    r = pygame.Rect(offset_x + x*scale, offset_y + y*scale, scale, scale)
                    pygame.draw.rect(self.screen, color, r)
            mini_px = offset_x + px*scale
            mini_py = offset_y + py*scale
            pygame.draw.rect(self.screen, COLOR_MINIMAP_PLAYER, (mini_px, mini_py, scale, scale))
            # if hint active, draw mini arrow (with alpha fade)
            if pinger_remaining > 0.0:
                ex, ey = self.exit_pos
                dx = ex - px
                dy = ey - py
                if dx != 0 or dy != 0:
                    angle = math.atan2(dy, dx)
                    line_len = max(6, int(scale * 3))
                    x1 = mini_px + scale/2
                    y1 = mini_py + scale/2
                    x2 = x1 + math.cos(angle)*line_len
                    y2 = y1 + math.sin(angle)*line_len
                    alpha = int(255 * (pinger_remaining / PINGER_SHOW_SEC))
                    tmp = pygame.Surface((mini_w, mini_h), pygame.SRCALPHA)
                    pygame.draw.line(tmp, (220,80,80, alpha), (x1 - mini_x, y1 - mini_y), (x2 - mini_x, y2 - mini_y), max(1, int(scale/6)))
                    self.screen.blit(tmp, (mini_x, mini_y))

    def draw(self):
        self.screen.fill(WINDOW_BG)
        if self.maze_surface.get_width() != self.maze_surface_w or self.maze_surface.get_height() != self.maze_surface_h:
            self.maze_surface = pygame.Surface((self.maze_surface_w, self.maze_surface_h))
        # default background hides entire maze
        self.maze_surface.fill(COLOR_HIDDEN)

        now = time.time()
        px, py = self.player_pos

        # Render radius around player for the visible neighborhood (2..4 tiles)
        render_r = max(2, min(4, self.reveal_radius))
        xmin = max(0, px - render_r)
        xmax = min(self.grid_w - 1, px + render_r)
        ymin = max(0, py - render_r)
        ymax = min(self.grid_h - 1, py + render_r)

        # draw only the small neighborhood (everywhere else remains hidden/background)
        for y in range(ymin, ymax + 1):
            for x in range(xmin, xmax + 1):
                sx = x * self.draw_tile
                sy = y * self.draw_tile
                vis = self.is_visible(x, y)
                if not vis:
                    pygame.draw.rect(self.maze_surface, COLOR_HIDDEN, (sx, sy, self.draw_tile, self.draw_tile))
                    continue
                if self.grid[y][x] == 1:
                    pygame.draw.rect(self.maze_surface, COLOR_WALL, (sx, sy, self.draw_tile, self.draw_tile))
                else:
                    # use level-specific floor color
                    pygame.draw.rect(self.maze_surface, self.floor_color, (sx, sy, self.draw_tile, self.draw_tile))

        # draw player as before
        prx = px * self.draw_tile + int(self.draw_tile * 0.15)
        pry = py * self.draw_tile + int(self.draw_tile * 0.15)
        psize = int(self.draw_tile * 0.7)
        pygame.draw.rect(self.maze_surface, COLOR_PLAYER, (prx, pry, psize, psize))

        # hint arrow (main view) with fade
        pinger_remaining = max(0.0, self.pinger_active_until - now)
        if pinger_remaining > 0.0:
            ex, ey = self.exit_pos
            dx = ex - px
            dy = ey - py
            angle = math.atan2(dy, dx) if (dx != 0 or dy != 0) else 0.0
            cx = px * self.draw_tile + self.draw_tile // 2
            cy = py * self.draw_tile + self.draw_tile // 2
            arrow_size = max(8, self.draw_tile // 2)
            alpha = int(255 * (pinger_remaining / PINGER_SHOW_SEC))
            self.draw_pinger_arrow(self.maze_surface, cx, cy, angle, arrow_size, alpha)

        # debug reveal of exit (unchanged)
        if self.debug_show_exit:
            ex, ey = self.exit_pos
            sx = ex * self.draw_tile
            sy = ey * self.draw_tile
            pad = max(2, self.draw_tile // 6)
            pygame.draw.rect(self.maze_surface, (220, 60, 60), (sx + pad, sy + pad, self.draw_tile - pad * 2, self.draw_tile - pad * 2))

        # blit maze_surface
        left_x = MARGIN
        left_y = MARGIN
        self.screen.blit(self.maze_surface, (left_x, left_y))

        # Draw top counter for hints & small info (always visible)
        top_center_x = self.win_w // 2
        self.draw_text(f"Hints used: {self.hint_count}", top_center_x - 80, 6, self.font, COLOR_TEXT)

        # HUD rendering: when not minimized -> full sidebar; when minimized -> only floating movable minimap
        hud_x = left_x + self.maze_surface_w + MARGIN
        hud_rect = pygame.Rect(hud_x, MARGIN, HUD_WIDTH, self.win_h - MARGIN*2)

        if not self.hud_minimized:
            pygame.draw.rect(self.screen, COLOR_HUD_BG, hud_rect, border_radius=6)
            pad = 12
            x_text = hud_x + pad
            y_text = MARGIN + pad

            # Build wrapped HUD lines
            lines = self.generate_hud_lines(x_text, pad)
            # compute content height
            line_heights = []
            for (txt, font, col) in lines:
                lh = font.get_linesize() if font != self.bigfont else self.bigfont.get_linesize()
                line_heights.append(lh)
            content_h = sum(line_heights)
            view_h = hud_rect.height - pad*2 - 40  # leaves room at top and bottom
            max_scroll = max(0, content_h - view_h)
            # clamp hud_scroll
            self.hud_scroll = clamp(self.hud_scroll, 0, max_scroll)

            # draw content into viewport with scroll offset
            draw_x = x_text
            draw_y = y_text - int(self.hud_scroll)
            cursor = 0
            for idx, (txt, font, col) in enumerate(lines):
                lh = line_heights[idx]
                # only render lines that intersect view rect
                if draw_y + lh >= hud_rect.y + pad and draw_y <= hud_rect.y + hud_rect.height - pad - 30:
                    surf = font.render(str(txt), True, col)
                    self.screen.blit(surf, (draw_x, draw_y))
                draw_y += lh
                cursor += 1

            # Buttons: HINT and MINIMIZE (positioned near bottom)
            btn_w = 120
            btn_h = 28
            btn_x = x_text
            btn_y = self.win_h - MARGIN - pad - btn_h - 30
            self.hint_button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            pygame.draw.rect(self.screen, COLOR_BUTTON, self.hint_button_rect, border_radius=6)
            self.draw_text("HINT", btn_x + 36, btn_y + 6, self.font, COLOR_BUTTON_TEXT)
            # Minimize button
            min_x = btn_x + btn_w + 12
            self.minimize_button_rect = pygame.Rect(min_x, btn_y, 28, btn_h)
            pygame.draw.rect(self.screen, COLOR_BUTTON, self.minimize_button_rect, border_radius=6)
            self.draw_text("-", min_x + 8, btn_y + 6, self.font, COLOR_BUTTON_TEXT)

            # draw minimap at bottom (since HUD visible) - not draggable in full HUD mode
            mini_w = HUD_WIDTH - pad*2
            mini_h = 160
            mini_x = x_text
            mini_y = btn_y - 14 - mini_h
            self.draw_minimap_at(mini_x, mini_y, mini_w, mini_h, px, py, pinger_remaining)

            # draw scrollbar at right side of HUD content
            scroll_x = hud_rect.right - 12
            track_y = hud_rect.y + pad + 8
            track_h = view_h
            track_rect = pygame.Rect(scroll_x, track_y, 8, track_h)
            pygame.draw.rect(self.screen, COLOR_SCROLL_TRACK, track_rect, border_radius=4)
            if content_h > 0 and max_scroll > 0:
                thumb_h = max(20, int(view_h * (view_h / content_h)))
                thumb_y = track_y + int((self.hud_scroll / max_scroll) * (track_h - thumb_h))
                thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_h)
                pygame.draw.rect(self.screen, COLOR_SCROLL_THUMB, thumb_rect, border_radius=4)
            else:
                thumb_rect = pygame.Rect(track_rect.x, track_rect.y, track_rect.width, track_rect.height)
                pygame.draw.rect(self.screen, COLOR_SCROLL_THUMB, thumb_rect, border_radius=4)

        else:
            # HUD fully hidden: show only floating minimap (draggable), no other sidebar UI.
            # initialize mini_pos to a default top-right over the maze if not set
            if self.mini_pos is None:
                default_x = left_x + max(0, self.maze_surface_w - self.mini_w - 12)
                default_y = left_y + 12
                default_x = int(clamp(default_x, left_x, left_x + max(0, self.maze_surface_w - self.mini_w)))
                default_y = int(clamp(default_y, left_y, left_y + max(0, self.maze_surface_h - self.mini_h)))
                self.mini_pos = (default_x, default_y)

            mini_x, mini_y = self.mini_pos
            # draw a thin outline to indicate draggable widget
            outline_rect = pygame.Rect(mini_x-4, mini_y-4, self.mini_w+8, self.mini_h+8)
            pygame.draw.rect(self.screen, (40,160,40), outline_rect, width=2, border_radius=6)
            # draw minimap contents
            self.draw_minimap_at(mini_x, mini_y, self.mini_w, self.mini_h, px, py, pinger_remaining)

            # small reminder text to restore HUD
            self.draw_text("[HUD hidden — press M to restore]", self.win_w - 260, 8, self.font, (140,140,140))

            # ensure button rects are None to avoid accidental clicks
            self.hint_button_rect = None
            self.minimize_button_rect = None

        # end draw

    def draw_text(self, text, x, y, font, color):
        surf = font.render(str(text), True, color)
        self.screen.blit(surf, (x, y))

    def run(self):
        try:
            while self.running:
                dt = self.clock.tick(FPS)
                self.handle_input()
                self.draw()
                pygame.display.flip()
        finally:
            cleanup_temp_sounds()
            pygame.quit()

# ---------- main ----------
def main():
    game = MazeGame(level=1)
    game.run()

if __name__ == "__main__":
    main()
