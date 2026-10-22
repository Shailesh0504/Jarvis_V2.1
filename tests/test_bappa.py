"""
✨ ॥ श्री गणेशाय नमः ॥ ✨

Interactive Fullscreen Step-by-Step Animated Drawing of Bhagwan Ganesha in Python.

Key Features:
- Native Fullscreen Mode (Press F11 or 'F' to toggle Fullscreen/Window)
- High-Resolution Dynamic Scaled Canvas (sharp on 1080p, 2K, 4K displays)
- Real-time animated strokes and traditional gold & saffron styling
- Keyboard Controls:
    [F11] / [F] : Toggle Fullscreen / Window Mode
    [Space]     : Instant Step Skip / Fast-forward
    [+ / -]     : Increase / Decrease Drawing Speed
    [R]         : Restart from the beginning
    [ESC]       : Exit Application
"""

import os
import sys
import math

import pytest

# Safety: ye pygame fullscreen app hai, pytest test nahi.
# Test collection ke samay GUI/fullscreen/sys.exit kabhi trigger nahi hona chahiye.
pytestmark = pytest.mark.skip(reason="GUI art app hai, automated pytest me run nahi karni chahiye.")

if os.environ.get("JARVIS_TEST_MODE") != "1" and "pytest" not in sys.modules:
    import pygame
else:
    pygame = None

# ----------------- Virtual Canvas Resolution & Palette -----------------
V_WIDTH, V_HEIGHT = 1200, 1200  # High-definition virtual canvas
FPS = 60

# Divine Traditional Colors
BG_BLACK    = (10, 10, 14)
GOLD_LIGHT  = (255, 240, 150)
GOLD        = (255, 210, 0)
GOLD_DARK   = (200, 150, 0)
SAFFRON     = (255, 115, 20)
SAFFRON_GLOW= (255, 160, 60)
RED_SINDOOR = (230, 25, 35)
DEEP_RED    = (150, 10, 20)
IVORY_WHITE = (255, 255, 245)
PEARL       = (250, 250, 255)
MODAK_GOLD  = (255, 220, 130)
DARK_OUTLINE= (45, 20, 30)

# ----------------- Curve & Geometry Utilities -----------------
def get_bezier_points(p0, p1, p2, p3=None, steps=50):
    """Calculates smooth interpolated points along Bezier curves."""
    points = []
    for i in range(steps + 1):
        t = i / float(steps)
        if p3 is None:
            # Quadratic Bezier
            x = (1 - t)**2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
            y = (1 - t)**2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        else:
            # Cubic Bezier
            x = ((1 - t)**3 * p0[0] + 3 * (1 - t)**2 * t * p1[0] +
                 3 * (1 - t) * t**2 * p2[0] + t**3 * p3[0])
            y = ((1 - t)**3 * p0[1] + 3 * (1 - t)**2 * t * p1[1] +
                 3 * (1 - t) * t**2 * p2[1] + t**3 * p3[1])
        points.append((x, y))
    return points

def get_arc_points(cx, cy, rx, ry, start_deg, end_deg, steps=60):
    points = []
    rad_start = math.radians(start_deg)
    rad_end = math.radians(end_deg)
    for i in range(steps + 1):
        t = i / float(steps)
        ang = rad_start + t * (rad_end - rad_start)
        x = cx + rx * math.cos(ang)
        y = cy + ry * math.sin(ang)
        points.append((x, y))
    return points


# ----------------- Step-by-Step Drawing Plan -----------------
def create_drawing_plan(cx, cy):
    """Generates the step-by-step vector sequence for Bhagwan Ganesha."""
    steps = []

    # ================= 1. DIVINE AURA & HALO (तेजोमय प्रभा मण्डल) =================
    s1_strokes = []
    # Radiant background halo rays
    for deg in range(0, 360, 12):
        rad = math.radians(deg)
        x1 = cx + math.cos(rad) * 360
        y1 = (cy - 50) + math.sin(rad) * 340
        x2 = cx + math.cos(rad) * 415
        y2 = (cy - 50) + math.sin(rad) * 395
        s1_strokes.append({'type': 'line', 'color': (140, 95, 20), 'pts': [(x1, y1), (x2, y2)], 'w': 2})

    # Concentric aura rings
    aura_outer = get_arc_points(cx, cy - 50, 350, 330, 0, 360, steps=100)
    s1_strokes.append({'type': 'curve', 'color': (190, 140, 40), 'pts': aura_outer, 'w': 4})
    aura_inner = get_arc_points(cx, cy - 50, 325, 305, 0, 360, steps=100)
    s1_strokes.append({'type': 'curve', 'color': (110, 75, 20), 'pts': aura_inner, 'w': 2})

    steps.append({"name": "1. दिव्य प्रभा मण्डल (Divine Radiance Halo)", "items": s1_strokes})

    # ================= 2. GRAND ROYAL CROWN / MUKUT (भव्य मुकुट) =================
    s2_strokes = []
    # Mukut base tier
    m_base = [
        (cx - 140, cy - 180), (cx + 140, cy - 180),
        (cx + 115, cy - 225), (cx - 115, cy - 225)
    ]
    s2_strokes.append({'type': 'fill_poly', 'color': GOLD_DARK, 'pts': m_base})
    s2_strokes.append({'type': 'poly', 'color': GOLD, 'pts': m_base, 'w': 4})

    # Mukut middle tier
    m_mid = [
        (cx - 110, cy - 225), (cx + 110, cy - 225),
        (cx + 75, cy - 300), (cx - 75, cy - 300)
    ]
    s2_strokes.append({'type': 'fill_poly', 'color': SAFFRON, 'pts': m_mid})
    s2_strokes.append({'type': 'poly', 'color': GOLD, 'pts': m_mid, 'w': 4})

    # Mukut top pinnacle (Triangular Kalash Cone)
    m_top = [(cx - 70, cy - 300), (cx + 70, cy - 300), (cx, cy - 415)]
    s2_strokes.append({'type': 'fill_poly', 'color': GOLD, 'pts': m_top})
    s2_strokes.append({'type': 'poly', 'color': GOLD_LIGHT, 'pts': m_top, 'w': 4})

    # Kalash jewels and crest gems
    s2_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx, cy - 425), 'r': 12, 'fill': True})
    s2_strokes.append({'type': 'circle', 'color': GOLD_LIGHT, 'center': (cx, cy - 445), 'r': 7, 'fill': True})
    s2_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx, cy - 202), 'r': 11, 'fill': True})
    s2_strokes.append({'type': 'circle', 'color': PEARL, 'center': (cx - 65, cy - 202), 'r': 8, 'fill': True})
    s2_strokes.append({'type': 'circle', 'color': PEARL, 'center': (cx + 65, cy - 202), 'r': 8, 'fill': True})
    s2_strokes.append({'type': 'circle', 'color': GOLD_LIGHT, 'center': (cx, cy - 262), 'r': 10, 'fill': True})

    steps.append({"name": "2. भव्य सुवर्ण मुकुट (Golden Crown & Crest)", "items": s2_strokes})

    # ================= 3. MAJESTIC EARS & KUNDAL (विशाल कर्ण एवं कुण्डल) =================
    s3_strokes = []
    # Left Ear gracefully sweeping
    l_ear_outer = get_bezier_points((cx - 110, cy - 165), (cx - 310, cy - 195), (cx - 310, cy + 50), (cx - 110, cy + 65), steps=45)
    l_ear_inner = get_bezier_points((cx - 110, cy - 125), (cx - 265, cy - 150), (cx - 265, cy + 25), (cx - 110, cy + 40), steps=40)
    s3_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': l_ear_outer, 'w': 7})
    s3_strokes.append({'type': 'curve', 'color': GOLD, 'pts': l_ear_inner, 'w': 3})

    # Right Ear gracefully sweeping
    r_ear_outer = get_bezier_points((cx + 110, cy - 165), (cx + 310, cy - 195), (cx + 310, cy + 50), (cx + 110, cy + 65), steps=45)
    r_ear_inner = get_bezier_points((cx + 110, cy - 125), (cx + 265, cy - 150), (cx + 265, cy + 25), (cx + 110, cy + 40), steps=40)
    s3_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': r_ear_outer, 'w': 7})
    s3_strokes.append({'type': 'curve', 'color': GOLD, 'pts': r_ear_inner, 'w': 3})

    # Golden Kundal (Ear Ornaments)
    s3_strokes.append({'type': 'circle', 'color': GOLD, 'center': (cx - 275, cy + 55), 'r': 18, 'fill': True})
    s3_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx - 275, cy + 55), 'r': 8, 'fill': True})
    s3_strokes.append({'type': 'circle', 'color': GOLD, 'center': (cx + 275, cy + 55), 'r': 18, 'fill': True})
    s3_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx + 275, cy + 55), 'r': 8, 'fill': True})

    steps.append({"name": "3. विशाल कर्ण एवं कुण्डल (Grand Divine Ears)", "items": s3_strokes})

    # ================= 4. MASTAK & SACRED TILAK (मस्तक एवं त्रिपुण्ड तिलक) =================
    s4_strokes = []
    # Forehead temple curves
    head_l = get_bezier_points((cx - 110, cy - 165), (cx - 135, cy - 65), (cx - 90, cy + 12), steps=35)
    head_r = get_bezier_points((cx + 110, cy - 165), (cx + 135, cy - 65), (cx + 90, cy + 12), steps=35)
    s4_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': head_l, 'w': 5})
    s4_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': head_r, 'w': 5})

    # Tripund (Sacred 3 sandalwood arcs across forehead)
    for dy in [-115, -100, -85]:
        t_arc = get_bezier_points((cx - 70, cy + dy), (cx, cy + dy - 8), (cx + 70, cy + dy), steps=30)
        s4_strokes.append({'type': 'curve', 'color': GOLD_LIGHT, 'pts': t_arc, 'w': 4})

    # Vertical Sindoor Tilak
    tilak_shape = [
        (cx - 9, cy - 128), (cx + 9, cy - 128),
        (cx + 12, cy - 58), (cx, cy - 32), (cx - 12, cy - 58)
    ]
    s4_strokes.append({'type': 'fill_poly', 'color': RED_SINDOOR, 'pts': tilak_shape})
    s4_strokes.append({'type': 'circle', 'color': GOLD_LIGHT, 'center': (cx, cy - 30), 'r': 6, 'fill': True})

    steps.append({"name": "4. पवित्र मस्तक एवं त्रिपुण्ड तिलक (Forehead & Tilak)", "items": s4_strokes})

    # ================= 5. DIVINE EYES & EYEBROWS (करुणामयी नयन) =================
    s5_strokes = []
    # Eyebrows
    l_brow = get_bezier_points((cx - 95, cy - 62), (cx - 58, cy - 80), (cx - 28, cy - 56), steps=30)
    r_brow = get_bezier_points((cx + 28, cy - 56), (cx + 58, cy - 80), (cx + 95, cy - 62), steps=30)
    s5_strokes.append({'type': 'curve', 'color': (65, 30, 15), 'pts': l_brow, 'w': 5})
    s5_strokes.append({'type': 'curve', 'color': (65, 30, 15), 'pts': r_brow, 'w': 5})

    # Left Eye
    l_eye_t = get_bezier_points((cx - 90, cy - 45), (cx - 60, cy - 64), (cx - 30, cy - 40), steps=30)
    l_eye_b = get_bezier_points((cx - 90, cy - 45), (cx - 60, cy - 26), (cx - 30, cy - 40), steps=30)
    s5_strokes.append({'type': 'curve', 'color': IVORY_WHITE, 'pts': l_eye_t, 'w': 4})
    s5_strokes.append({'type': 'curve', 'color': IVORY_WHITE, 'pts': l_eye_b, 'w': 4})
    s5_strokes.append({'type': 'circle', 'color': (20, 15, 20), 'center': (cx - 60, cy - 45), 'r': 8, 'fill': True})
    s5_strokes.append({'type': 'circle', 'color': IVORY_WHITE, 'center': (cx - 62, cy - 47), 'r': 3, 'fill': True})

    # Right Eye
    r_eye_t = get_bezier_points((cx + 30, cy - 40), (cx + 60, cy - 64), (cx + 90, cy - 45), steps=30)
    r_eye_b = get_bezier_points((cx + 30, cy - 40), (cx + 60, cy - 26), (cx + 90, cy - 45), steps=30)
    s5_strokes.append({'type': 'curve', 'color': IVORY_WHITE, 'pts': r_eye_t, 'w': 4})
    s5_strokes.append({'type': 'curve', 'color': IVORY_WHITE, 'pts': r_eye_b, 'w': 4})
    s5_strokes.append({'type': 'circle', 'color': (20, 15, 20), 'center': (cx + 60, cy - 45), 'r': 8, 'fill': True})
    s5_strokes.append({'type': 'circle', 'color': IVORY_WHITE, 'center': (cx + 58, cy - 47), 'r': 3, 'fill': True})

    steps.append({"name": "5. करुणामयी नयन (Merciful Divine Eyes)", "items": s5_strokes})

    # ================= 6. VAKRATUNDA / CURVED TRUNK (वक्रतुण्ड सूंड) =================
    s6_strokes = []
    # Left contour of trunk curving smoothly
    suund_l = get_bezier_points(
        (cx - 30, cy + 6),
        (cx - 50, cy + 140),
        (cx + 75, cy + 220),
        (cx - 20, cy + 310),
        steps=55
    )
    # Right contour of trunk
    suund_r = get_bezier_points(
        (cx + 30, cy + 6),
        (cx + 12, cy + 140),
        (cx + 150, cy + 210),
        (cx + 18, cy + 335),
        steps=55
    )
    # Elegant trunk curl
    suund_curl = get_bezier_points(
        (cx + 18, cy + 335),
        (cx - 85, cy + 335),
        (cx - 110, cy + 260),
        (cx - 40, cy + 248),
        steps=40
    )

    s6_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': suund_l, 'w': 8})
    s6_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': suund_r, 'w': 8})
    s6_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': suund_curl, 'w': 8})

    # Golden bands / rings on trunk
    for dy in [75, 132, 190]:
        t_band = get_bezier_points((cx - 20, cy + dy), (cx + 18, cy + dy + 10), (cx + 50, cy + dy), steps=25)
        s6_strokes.append({'type': 'curve', 'color': GOLD, 'pts': t_band, 'w': 4})

    # Tip Bell / Ornament
    s6_strokes.append({'type': 'circle', 'color': GOLD, 'center': (cx - 40, cy + 248), 'r': 12, 'fill': True})
    s6_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx - 40, cy + 248), 'r': 5, 'fill': True})

    steps.append({"name": "6. वक्रतुण्ड सूंड एवं आभूषण (Curved Trunk & Ornaments)", "items": s6_strokes})

    # ================= 7. EKDANTA (दाँत - एकदंत स्वरूप) =================
    s7_strokes = []
    # Right full unbroken tusk
    r_tusk = [(cx + 36, cy + 18), (cx + 82, cy + 76), (cx + 48, cy + 38)]
    s7_strokes.append({'type': 'fill_poly', 'color': IVORY_WHITE, 'pts': r_tusk})
    s7_strokes.append({'type': 'poly', 'color': GOLD, 'pts': r_tusk, 'w': 3})

    # Left sacred broken tusk (Khandit Dant)
    l_tusk = [(cx - 36, cy + 18), (cx - 62, cy + 48), (cx - 45, cy + 32)]
    s7_strokes.append({'type': 'fill_poly', 'color': IVORY_WHITE, 'pts': l_tusk})
    s7_strokes.append({'type': 'poly', 'color': GOLD, 'pts': l_tusk, 'w': 3})

    steps.append({"name": "7. एकदंत स्वरूप (Holy Ekdanta)", "items": s7_strokes})

    # ================= 8. ABHAYA HASTA & MODAK PATRA (हाथ एवं मोदक पात्र) =================
    s8_strokes = []
    # Right Hand Arm (Abhaya Hasta - Blessing posture)
    r_arm = get_bezier_points((cx + 115, cy + 115), (cx + 250, cy + 155), (cx + 290, cy + 235), steps=40)
    s8_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': r_arm, 'w': 8})

    # Blessing Palm
    palm_pts = [
        (cx + 275, cy + 225), (cx + 320, cy + 200),
        (cx + 345, cy + 235), (cx + 325, cy + 285), (cx + 288, cy + 275)
    ]
    s8_strokes.append({'type': 'fill_poly', 'color': (245, 155, 75), 'pts': palm_pts})
    s8_strokes.append({'type': 'poly', 'color': GOLD, 'pts': palm_pts, 'w': 3})
    s8_strokes.append({'type': 'circle', 'color': RED_SINDOOR, 'center': (cx + 312, cy + 240), 'r': 12, 'fill': True})
    s8_strokes.append({'type': 'circle', 'color': GOLD_LIGHT, 'center': (cx + 312, cy + 240), 'r': 5, 'fill': True})

    # Left Hand Arm holding Modak Bowl
    l_arm = get_bezier_points((cx - 115, cy + 115), (cx - 230, cy + 165), (cx - 275, cy + 270), steps=40)
    s8_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': l_arm, 'w': 8})

    # Golden Modak Bowl
    bowl_pts = [
        (cx - 320, cy + 280), (cx - 230, cy + 280),
        (cx - 250, cy + 325), (cx - 300, cy + 325)
    ]
    s8_strokes.append({'type': 'fill_poly', 'color': GOLD, 'pts': bowl_pts})
    s8_strokes.append({'type': 'poly', 'color': GOLD_LIGHT, 'pts': bowl_pts, 'w': 3})

    # Delicious Modaks
    modaks = [(-292, 265), (-275, 260), (-258, 265), (-275, 242)]
    for mx, my in modaks:
        s8_strokes.append({'type': 'circle', 'color': MODAK_GOLD, 'center': (cx + mx, cy + my), 'r': 11, 'fill': True})
        s8_strokes.append({'type': 'circle', 'color': SAFFRON, 'center': (cx + mx, cy + my - 8), 'r': 4, 'fill': True})

    steps.append({"name": "8. वरद हस्त एवं मोदक पात्र (Blessings & Modaks)", "items": s8_strokes})

    # ================= 9. PITAMBAR, JANEHU & MALA (पीताम्बर, जनेऊ व माला) =================
    s9_strokes = []
    # Lower Body & Silk Drapes (curved seated posture)
    body_l = get_bezier_points((cx - 140, cy + 215), (cx - 305, cy + 395), (cx - 150, cy + 460), steps=40)
    body_r = get_bezier_points((cx + 140, cy + 215), (cx + 305, cy + 395), (cx + 150, cy + 460), steps=40)
    body_b = get_bezier_points((cx - 150, cy + 460), (cx, cy + 480), (cx + 150, cy + 460), steps=40)
    s9_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': body_l, 'w': 8})
    s9_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': body_r, 'w': 8})
    s9_strokes.append({'type': 'curve', 'color': SAFFRON, 'pts': body_b, 'w': 8})

   

    # Angavastram / Pitamber Golden Border Fold
    fold_l = get_bezier_points((cx - 140, cy + 260), (cx - 60, cy + 370), (cx - 120, cy + 440), steps=35)
    fold_r = get_bezier_points((cx + 140, cy + 260), (cx + 60, cy + 370), (cx + 120, cy + 440), steps=35)
    s9_strokes.append({'type': 'curve', 'color': GOLD, 'pts': fold_l, 'w': 3})
    s9_strokes.append({'type': 'curve', 'color': GOLD, 'pts': fold_r, 'w': 3})

    # Pearl Necklace / Mala (मुक्ता माला)
    for i in range(15):
        t = i / 14.0
        mx = (cx - 110) * (1 - t) + (cx + 110) * t
        my = cy + 135 + math.sin(t * math.pi) * 80
        s9_strokes.append({'type': 'circle', 'color': PEARL, 'center': (int(mx), int(my)), 'r': 6, 'fill': True})
        s9_strokes.append({'type': 'circle', 'color': GOLD, 'center': (int(mx), int(my)), 'r': 3, 'fill': True})

    steps.append({"name": "9. पीताम्बर, जनेऊ एवं मुक्ताहार (Sacred Attire & Pearl Mala)", "items": s9_strokes})

    # ================= 10. MAHAMANTRA & DIVINE BLESSINGS =================
    s10_strokes = []
    # Auspicious celestial glow stars
    star_positions = [
        (cx - 370, cy - 320), (cx + 370, cy - 320),
        (cx - 410, cy - 100), (cx + 410, cy - 100),
        (cx - 380, cy + 150), (cx + 380, cy + 150),
        (cx - 330, cy + 330), (cx + 330, cy + 330),
    ]
    for sx, sy in star_positions:
        s10_strokes.append({'type': 'circle', 'color': GOLD_LIGHT, 'center': (sx, sy), 'r': 5, 'fill': True})
        s10_strokes.append({'type': 'circle', 'color': SAFFRON, 'center': (sx, sy), 'r': 11, 'fill': False})

    steps.append({"name": "10. ॥ ॐ गं गणपतये नमः ॥ (Param Shanti & Blessings)", "items": s10_strokes})

    return steps


# ----------------- Rendering Engine for Items -----------------
def render_item(surface, item, progress=1.0):
    """Draws a single graphic item with stroke animation interpolation."""
    itype = item['type']
    color = item['color']

    if itype in ('curve', 'line'):
        pts = item['pts']
        w = item.get('w', 2)
        if len(pts) >= 2:
            count = max(2, int(len(pts) * progress))
            drawn_pts = [(int(x), int(y)) for x, y in pts[:count]]
            pygame.draw.lines(surface, color, False, drawn_pts, w)

    elif itype == 'fill_poly':
        pts = item['pts']
        if progress >= 1.0:
            pygame.draw.polygon(surface, color, [(int(x), int(y)) for x, y in pts])

    elif itype == 'poly':
        pts = item['pts']
        w = item.get('w', 2)
        if len(pts) >= 2:
            count = max(2, int(len(pts) * progress))
            drawn_pts = [(int(x), int(y)) for x, y in pts[:count]]
            if progress >= 1.0:
                pygame.draw.polygon(surface, color, drawn_pts, w)
            else:
                pygame.draw.lines(surface, color, False, drawn_pts, w)

    elif itype == 'circle':
        if progress >= 0.5:
            cx, cy = item['center']
            r = item['r']
            fill = item.get('fill', True)
            w = 0 if fill else 2
            pygame.draw.circle(surface, color, (int(cx), int(cy)), int(r), w)


# ----------------- UI Drawing Helpers -----------------
def draw_virtual_ui(surface, fonts, current_step_idx, total_steps, step_name, is_complete):
    """Draws all headers, mantras, and progress bars directly on high-res virtual canvas."""
    f_title, f_sub, f_mantra, f_ui = fonts

    # Top Header Mantra
    mantra_txt = " OM SHREE GANESHAYA NAMAHA "
    mantra_surf = f_mantra.render(mantra_txt, True, GOLD_LIGHT)
    surface.blit(mantra_surf, (V_WIDTH // 2 - mantra_surf.get_width() // 2, 28))

    

    # Bottom Step Title & Progress Bar
    bar_y = V_HEIGHT - 110
    panel_rect = pygame.Rect(50, bar_y - 15, V_WIDTH - 100, 95)

    # Semi-transparent dark panel
    panel_surf = pygame.Surface((panel_rect.width, panel_rect.height), pygame.SRCALPHA)
    panel_surf.fill((18, 16, 24, 235))
    surface.blit(panel_surf, (panel_rect.x, panel_rect.y))
    pygame.draw.rect(surface, GOLD_DARK, panel_rect, width=2, border_radius=10)

    # Step Label
    step_label = f"चरण {current_step_idx + 1}/{total_steps} :  {step_name}"
    step_surf = f_title.render(step_label, True, GOLD if not is_complete else GOLD_LIGHT)
    surface.blit(step_surf, (panel_rect.x + 25, bar_y - 5))

    # Progress Bar
    p_bar_w = V_WIDTH - 150
    p_bar_h = 12
    p_bar_y = bar_y + 44
    pygame.draw.rect(surface, (50, 45, 60), (panel_rect.x + 25, p_bar_y, p_bar_w, p_bar_h), border_radius=6)

    progress_frac = min(1.0, (current_step_idx + 1) / float(total_steps))
    filled_w = int(p_bar_w * progress_frac)
    if filled_w > 0:
        pygame.draw.rect(surface, GOLD, (panel_rect.x + 25, p_bar_y, filled_w, p_bar_h), border_radius=6)

    # Controls Info
    controls_txt = "[F11 / F]: Fullscreen  |  [Space]: Skip  |  [+ / -]: Speed  |  [R]: Restart  |  [ESC]: Exit"
    ctrl_surf = f_ui.render(controls_txt, True, (170, 165, 185))
    surface.blit(ctrl_surf, (V_WIDTH // 2 - ctrl_surf.get_width() // 2, V_HEIGHT - 25))


# ----------------- Dynamic Screen Display Helper -----------------
def get_display_scale_and_rect(screen_w, screen_h):
    """Calculates aspect-ratio preserving viewport bounds for any screen size."""
    scale = min(screen_w / float(V_WIDTH), screen_h / float(V_HEIGHT))
    scaled_w = int(V_WIDTH * scale)
    scaled_h = int(V_HEIGHT * scale)
    offset_x = (screen_w - scaled_w) // 2
    offset_y = (screen_h - scaled_h) // 2
    return scale, (offset_x, offset_y, scaled_w, scaled_h)


# ----------------- Main Loop -----------------
def main():
    # Safety: pytest/app-test ke dauran fullscreen GUI kabhi open nahi honi chahiye.
    if os.environ.get("JARVIS_TEST_MODE") == "1" or "pytest" in sys.modules or pygame is None:
        raise RuntimeError("test_bappa GUI main() pytest me run nahi ho sakta (safety guard).")
    pygame.init()
    pygame.font.init()

    # Detect desktop display size
    disp_info = pygame.display.Info()
    desktop_w, desktop_h = disp_info.current_w, disp_info.current_h

    # Start in Fullscreen mode by default
    fullscreen = True
    screen = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN | pygame.DOUBLEBUF)
    pygame.display.set_caption("॥ श्री गणेशाय नमः ॥ - Bhagwan Ganesha Step-by-Step Drawing")
    clock = pygame.time.Clock()

    # Fonts
    font_mantra = pygame.font.SysFont("Nirmala UI", 38, bold=True)
    font_sub = pygame.font.SysFont("Nirmala UI", 22)
    font_title = pygame.font.SysFont("Nirmala UI", 28, bold=True)
    font_ui = pygame.font.SysFont("Arial", 18)
    fonts = (font_title, font_sub, font_mantra, font_ui)

    # Virtual high-resolution drawing surface
    virtual_canvas = pygame.Surface((V_WIDTH, V_HEIGHT))
    completed_canvas = pygame.Surface((V_WIDTH, V_HEIGHT))
    completed_canvas.fill(BG_BLACK)

    cx, cy = V_WIDTH // 2, 570
    steps = create_drawing_plan(cx, cy)
    total_steps = len(steps)

    step_idx = 0
    item_idx = 0
    stroke_progress = 0.0
    drawing_speed = 0.05
    is_finished = False
    running = True

    while running:
        cur_w, cur_h = screen.get_size()

        # 1. Event Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                # Toggle Fullscreen / Windowed Mode
                elif event.key in (pygame.K_F11, pygame.K_f):
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((desktop_w, desktop_h), pygame.FULLSCREEN | pygame.DOUBLEBUF)
                    else:
                        screen = pygame.display.set_mode((960, 960), pygame.RESIZABLE | pygame.DOUBLEBUF)

                # Skip current step
                elif event.key == pygame.K_SPACE:
                    if step_idx < total_steps:
                        cur_items = steps[step_idx]['items']
                        for it in cur_items:
                            render_item(completed_canvas, it, 1.0)
                        step_idx += 1
                        item_idx = 0
                        stroke_progress = 0.0
                        if step_idx >= total_steps:
                            is_finished = True

                # Restart
                elif event.key == pygame.K_r:
                    completed_canvas.fill(BG_BLACK)
                    step_idx = 0
                    item_idx = 0
                    stroke_progress = 0.0
                    is_finished = False

                # Speed control
                elif event.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                    drawing_speed = min(0.25, drawing_speed + 0.02)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    drawing_speed = max(0.01, drawing_speed - 0.01)

            elif event.type == pygame.VIDEORESIZE and not fullscreen:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE | pygame.DOUBLEBUF)

        # 2. Animation Stepper
        if not is_finished and step_idx < total_steps:
            cur_step = steps[step_idx]
            cur_items = cur_step['items']

            if item_idx < len(cur_items):
                stroke_progress += drawing_speed
                if stroke_progress >= 1.0:
                    render_item(completed_canvas, cur_items[item_idx], 1.0)
                    item_idx += 1
                    stroke_progress = 0.0
            else:
                step_idx += 1
                item_idx = 0
                stroke_progress = 0.0
                if step_idx >= total_steps:
                    is_finished = True

        # 3. Composite onto Virtual High-Res Canvas
        virtual_canvas.blit(completed_canvas, (0, 0))

        if not is_finished and step_idx < total_steps:
            cur_items = steps[step_idx]['items']
            if item_idx < len(cur_items):
                render_item(virtual_canvas, cur_items[item_idx], stroke_progress)

        current_name = steps[step_idx]['name'] if step_idx < total_steps else "॥ पूर्ण दर्शन - मंगलमय आशीर्वाद ॥"
        draw_virtual_ui(virtual_canvas, fonts, min(step_idx, total_steps - 1), total_steps, current_name, is_finished)

        # 4. Scale and Blit onto Screen with Aspect-Ratio Letterboxing
        screen.fill(BG_BLACK)
        scale, (off_x, off_y, sc_w, sc_h) = get_display_scale_and_rect(cur_w, cur_h)
        scaled_surf = pygame.transform.smoothscale(virtual_canvas, (sc_w, sc_h))
        screen.blit(scaled_surf, (off_x, off_y))

        # 5. Flip & Tick
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()