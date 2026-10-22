# plugins/automation/drawings/bappa_drawing.py
"""
Bappa Drawing using Python Turtle Graphics.
Draws Lord Ganesha (Bappa) with animated strokes.
"""

import sys


def draw_bappa():
    """Executes the turtle drawing of Lord Ganesha (Bappa)."""
    import turtle
    import math

    # -------------------------------------------------
    # BAPPA DRAWING USING PYTHON TURTLE
    # -------------------------------------------------

    screen = turtle.Screen()
    screen.setup(1000, 900)
    screen.bgcolor("#FFFDF8")
    screen.title("Shree Ganesh - Bappa")

    t = turtle.Turtle()
    t.speed(0)
    t.hideturtle()
    t.pensize(3)

    # -------------------------------------------------
    # BASIC HELPERS
    # -------------------------------------------------

    def move(x, y):
        t.penup()
        t.goto(x, y)
        t.pendown()


    def filled_circle(x, y, radius, fill, outline="#222222"):
        move(x, y - radius)
        t.setheading(0)
        t.fillcolor(fill)
        t.pencolor(outline)
        t.begin_fill()
        t.circle(radius)
        t.end_fill()


    def polygon(points, fill, outline="#222222"):
        move(*points[0])
        t.fillcolor(fill)
        t.pencolor(outline)
        t.begin_fill()

        for point in points[1:]:
            t.goto(*point)

        t.goto(*points[0])
        t.end_fill()


    def line(points, width=3):
        t.pensize(width)
        move(*points[0])

        for point in points[1:]:
            t.goto(*point)


    def ellipse(x, y, rx, ry, fill, outline="#222222"):
        move(x, y)
        t.pencolor(outline)
        t.fillcolor(fill)

        t.begin_fill()

        for angle in range(361):
            rad = math.radians(angle)
            px = x + rx * math.cos(rad)
            py = y + ry * math.sin(rad)

            if angle == 0:
                t.goto(px, py)
            else:
                t.goto(px, py)

        t.end_fill()


    # -------------------------------------------------
    # BACKGROUND DECORATION
    # -------------------------------------------------

    # Decorative halo
    filled_circle(0, 130, 310, "#FFF1B8", "#F2C94C")
    filled_circle(0, 130, 285, "#FFFDF8", "#F2C94C")

    # -------------------------------------------------
    # SEAT / THRONE
    # -------------------------------------------------

    polygon(
        [
            (-300, -300),
            (300, -300),
            (335, -345),
            (-335, -345)
        ],
        "#D62828",
        "#8B1E1E"
    )

    polygon(
        [
            (-330, -345),
            (330, -345),
            (315, -390),
            (-315, -390)
        ],
        "#F5B700",
        "#9A6A00"
    )

    # Seat decoration
    for x in range(-270, 271, 90):
        filled_circle(x, -367, 12, "#FFDD57", "#9A6A00")


    # -------------------------------------------------
    # BODY
    # -------------------------------------------------

    ellipse(
        0,
        -70,
        190,
        210,
        "#F6B45B",
        "#222222"
    )

    # Belly
    ellipse(
        0,
        -105,
        135,
        145,
        "#FFC76D",
        "#222222"
    )

    # -------------------------------------------------
    # LEGS
    # -------------------------------------------------

    # Left leg
    ellipse(
        -105,
        -245,
        115,
        55,
        "#FFC107",
        "#222222"
    )

    # Right leg
    ellipse(
        105,
        -245,
        115,
        55,
        "#FFC107",
        "#222222"
    )

    # Feet
    ellipse(
        -45,
        -305,
        65,
        32,
        "#F6B45B",
        "#222222"
    )

    ellipse(
        45,
        -305,
        65,
        32,
        "#F6B45B",
        "#222222"
    )


    # -------------------------------------------------
    # EARS
    # -------------------------------------------------

    ellipse(
        -180,
        125,
        105,
        125,
        "#F6B45B",
        "#222222"
    )

    ellipse(
        180,
        125,
        105,
        125,
        "#F6B45B",
        "#222222"
    )

    ellipse(
        -180,
        125,
        72,
        92,
        "#F58A8A",
        "#D45B5B"
    )

    ellipse(
        180,
        125,
        72,
        92,
        "#F58A8A",
        "#D45B5B"
    )


    # -------------------------------------------------
    # HEAD
    # -------------------------------------------------

    filled_circle(
        0,
        145,
        190,
        "#F6B45B",
        "#222222"
    )

    # Face highlight
    ellipse(
        0,
        175,
        135,
        125,
        "#FFC76D",
        "#FFC76D"
    )


    # -------------------------------------------------
    # CROWN
    # -------------------------------------------------

    # Crown base
    polygon(
        [
            (-140, 290),
            (140, 290),
            (120, 335),
            (-120, 335)
        ],
        "#F5B700",
        "#9A6A00"
    )

    # Crown upper section
    polygon(
        [
            (-105, 335),
            (105, 335),
            (75, 415),
            (0, 465),
            (-75, 415)
        ],
        "#FFD54F",
        "#9A6A00"
    )

    # Crown top
    polygon(
        [
            (-35, 455),
            (0, 510),
            (35, 455)
        ],
        "#F5B700",
        "#9A6A00"
    )

    # Crown jewel
    filled_circle(
        0,
        385,
        27,
        "#E63946",
        "#9A1F28"
    )

    # Crown side jewels
    for x in [-75, -35, 35, 75]:
        filled_circle(x, 350, 10, "#2EAA59", "#166534")


    # -------------------------------------------------
    # EYES
    # -------------------------------------------------

    filled_circle(-65, 190, 28, "#FFFDF8", "#222222")
    filled_circle(65, 190, 28, "#FFFDF8", "#222222")

    filled_circle(-65, 190, 14, "#222222", "#111111")
    filled_circle(65, 190, 14, "#222222", "#111111")

    filled_circle(-60, 197, 5, "#FFFFFF", "#FFFFFF")
    filled_circle(70, 197, 5, "#FFFFFF", "#FFFFFF")


    # -------------------------------------------------
    # TILAK
    # -------------------------------------------------

    polygon(
        [
            (-18, 260),
            (0, 300),
            (18, 260),
            (0, 275)
        ],
        "#D62828",
        "#A61E1E"
    )

    filled_circle(
        0,
        252,
        7,
        "#D62828",
        "#D62828"
    )


    # -------------------------------------------------
    # TRUNK
    # -------------------------------------------------

    # Main trunk
    t.pensize(20)
    t.pencolor("#F6B45B")
    move(0, 135)

    t.setheading(-65)
    t.circle(105, 85)
    t.circle(-70, 75)

    # Trunk outline accent
    t.pensize(3)
    t.pencolor("#222222")

    move(-6, 130)
    t.setheading(-65)
    t.circle(105, 85)
    t.circle(-70, 75)

    # Trunk tip
    ellipse(
        55,
        65,
        55,
        30,
        "#F6B45B",
        "#222222"
    )


    # -------------------------------------------------
    # TUSKS
    # -------------------------------------------------

    polygon(
        [
            (-55, 80),
            (-105, 30),
            (-38, 55)
        ],
        "#FFFDF8",
        "#222222"
    )

    polygon(
        [
            (55, 80),
            (105, 30),
            (38, 55)
        ],
        "#FFFDF8",
        "#222222"
    )


    # -------------------------------------------------
    # NECKLACE
    # -------------------------------------------------

    t.pensize(7)
    t.pencolor("#F5B700")

    move(-100, 55)
    t.goto(0, 0)
    t.goto(100, 55)

    filled_circle(0, 0, 25, "#E63946", "#9A1F28")


    # -------------------------------------------------
    # LEFT ARM
    # -------------------------------------------------

    # Upper arm
    ellipse(
        -205,
        25,
        45,
        120,
        "#F6B45B",
        "#222222"
    )

    # Hand
    filled_circle(
        -225,
        -85,
        38,
        "#F6B45B",
        "#222222"
    )

    # Palm blessing
    polygon(
        [
            (-245, -50),
            (-220, 15),
            (-195, -50),
            (-200, -115),
            (-235, -115)
        ],
        "#F6B45B",
        "#222222"
    )

    # Om symbol
    t.pencolor("#D62828")
    t.pensize(4)

    move(-230, -85)
    t.write("ॐ", font=("Arial", 28, "bold"))


    # -------------------------------------------------
    # RIGHT ARM + LOTUS
    # -------------------------------------------------

    ellipse(
        205,
        25,
        45,
        120,
        "#F6B45B",
        "#222222"
    )

    # Hand
    filled_circle(
        225,
        105,
        35,
        "#F6B45B",
        "#222222"
    )

    # Lotus stem
    line(
        [
            (225, 125),
            (225, 220)
        ],
        7
    )

    # Lotus petals
    polygon(
        [
            (225, 210),
            (190, 250),
            (225, 235),
            (260, 250)
        ],
        "#FF4D8D",
        "#B83267"
    )

    ellipse(
        225,
        245,
        32,
        45,
        "#FF4D8D",
        "#B83267"
    )


    # -------------------------------------------------
    # LADDoo BOWL
    # -------------------------------------------------

    # Arm holding bowl
    ellipse(
        175,
        -55,
        80,
        40,
        "#F6B45B",
        "#222222"
    )

    # Bowl
    polygon(
        [
            (120, -120),
            (265, -120),
            (240, -175),
            (145, -175)
        ],
        "#F5B700",
        "#9A6A00"
    )

    # Laddoos
    for x, y in [
        (150, -120),
        (185, -105),
        (220, -120),
        (160, -150),
        (200, -145),
        (235, -150)
    ]:
        filled_circle(
            x,
            y,
            18,
            "#E9A23B",
            "#9A5B16"
        )


    # -------------------------------------------------
    # DHAKSHINA / CLOTH
    # -------------------------------------------------

    polygon(
        [
            (-170, -145),
            (-110, -190),
            (0, -175),
            (110, -190),
            (170, -145),
            (130, -250),
            (0, -225),
            (-130, -250)
        ],
        "#D62828",
        "#8B1E1E"
    )

    # Green waist cloth
    polygon(
        [
            (-120, -170),
            (120, -170),
            (95, -220),
            (0, -235),
            (-95, -220)
        ],
        "#2E8B57",
        "#155C38"
    )


    # -------------------------------------------------
    # MOUSE
    # -------------------------------------------------

    # Mouse body
    ellipse(
        390,
        -315,
        65,
        45,
        "#5B4636",
        "#222222"
    )

    # Mouse head
    filled_circle(
        440,
        -285,
        43,
        "#6B5140",
        "#222222"
    )

    # Ears
    filled_circle(
        415,
        -245,
        23,
        "#F19A9A",
        "#222222"
    )

    filled_circle(
        455,
        -245,
        23,
        "#F19A9A",
        "#222222"
    )

    # Eye
    filled_circle(
        452,
        -290,
        7,
        "#111111",
        "#111111"
    )

    # Nose
    filled_circle(
        478,
        -305,
        6,
        "#E63946",
        "#7A1720"
    )

    # Mouse tail
    t.pensize(4)
    t.pencolor("#5B4636")

    move(340, -325)
    t.setheading(210)
    t.circle(55, 160)


    # -------------------------------------------------
    # DECORATIVE FLOWERS
    # -------------------------------------------------

    def flower(x, y, scale=1):
        colors = ["#FF4D8D", "#FF6B9A", "#FF85AB", "#FF4D8D"]

        for angle in range(0, 360, 60):
            rad = math.radians(angle)

            px = x + math.cos(rad) * 30 * scale
            py = y + math.sin(rad) * 30 * scale

            ellipse(
                px,
                py,
                20 * scale,
                32 * scale,
                colors[(angle // 60) % len(colors)],
                "#B83267"
            )

        filled_circle(
            x,
            y,
            15 * scale,
            "#FFD54F",
            "#9A6A00"
        )


    flower(-390, 315, 0.8)
    flower(390, 315, 0.8)


    # -------------------------------------------------
    # FINAL TEXT
    # -------------------------------------------------

    move(-175, 430)
    t.pencolor("#D62828")
    t.write(
        "॥ श्री गणेशाय नमः ॥",
        font=("Arial", 24, "bold")
    )




if __name__ == "__main__":
    draw_bappa()
