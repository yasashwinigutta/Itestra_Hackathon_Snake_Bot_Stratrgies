from collections import deque

# ==========================================================
# MOVES
# ==========================================================

DIRECTIONS = {
    "NORTH": (0, -1),
    "SOUTH": (0, 1),
    "WEST": (-1, 0),
    "EAST": (1, 0),
}

OPPOSITE = {
    "NORTH": "SOUTH",
    "SOUTH": "NORTH",
    "WEST": "EAST",
    "EAST": "WEST",
}


def emergency_escape_score(pos, obstacles, size):
    w, h = size
    escape = 0

    for dx, dy in DIRECTIONS.values():
        n = (pos[0] + dx) % w, (pos[1] + dy) % h
        if n not in obstacles:
            escape += 1

    if escape <= 1:
        return -10000
    if escape == 2:
        return -2000
    return 0

# ==========================================================
# WRAP DISTANCE
# ==========================================================

def wrap_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(pos, w, h):
    return (pos[0] % w, pos[1] % h)


# ==========================================================
# FLOOD FILL (WRAP-SAFE)
# ==========================================================

def flood_fill(start, blocked, size, limit=500):
    if start in blocked:
        return 0

    w, h = size
    q = deque([start])
    seen = {start}
    count = 0

    while q and count < limit:
        cur = q.popleft()
        count += 1

        for dx, dy in DIRECTIONS.values():
            nxt = wrap((cur[0] + dx, cur[1] + dy), w, h)

            if nxt in blocked or nxt in seen:
                continue

            seen.add(nxt)
            q.append(nxt)

    return count


# ==========================================================
# ENEMY ZONES (SIMPLIFIED + LESS OVERPOWERED)
# ==========================================================

def enemy_zones(snakes, my_head, size):
    w, h = size

    z1, z2, z3 = set(), set(), set()

    for s in snakes:
        head = s["head"]
        if head == my_head:
            continue

        body = set(s.get("body", []))

        for dx, dy in DIRECTIONS.values():
            n1 = wrap((head[0] + dx, head[1] + dy), w, h)
            z1.add(n1)

            n2 = wrap((n1[0] + dx, n1[1] + dy), w, h)
            z2.add(n2)

            n3 = wrap((n2[0] + dx, n2[1] + dy), w, h)
            z3.add(n3)

        z1 -= body
        z2 -= body
        z3 -= body

    return z1, z2, z3


# ==========================================================
# ITEMS
# ==========================================================

def classify_items(items):
    apples, bad, stars = [], [], []

    for it in items:
        kind = str(it.kind).lower()
        pos = it.position

        if "star" in kind:
            stars.append(pos)
        elif "bad" in kind:
            bad.append(pos)
        elif "apple" in kind:
            if "bad" in kind:
                bad.append(pos)
            else:
                apples.append(pos)

    return apples, bad, stars


# ==========================================================
# CONTEXT CHECK
# ==========================================================

def is_contested(pos, my_head, snakes, size):
    w, h = size
    my_d = wrap_dist(my_head, pos, w, h)

    for s in snakes:
        if s["head"] == my_head:
            continue
        if wrap_dist(s["head"], pos, w, h) <= my_d:
            return True

    return False


# ==========================================================
# 1-STEP LOOKAHEAD SAFETY (CRITICAL FIX)
# ==========================================================

def has_escape(nxt, blocked, size):
    w, h = size

    for dx, dy in DIRECTIONS.values():
        nn = wrap((nxt[0] + dx, nxt[1] + dy), w, h)
        if nn not in blocked:
            return True

    return False


# ==========================================================
# MAIN STRATEGY
# ==========================================================

def choose_next_move(
    my_head,
    obstacles,
    snakes,
    field_size,
    items,
    current_direction
):
    w, h = field_size

    my_snake = next((s for s in snakes if s["head"] == my_head), None)
    own_body = set(my_snake.get("body", [])) if my_snake else set()

    apples, bad_apples, stars = classify_items(items)

    z1, z2, z3 = enemy_zones(snakes, my_head, field_size)

    best_move = current_direction
    best_score = -1e18

    for move, delta in DIRECTIONS.items():

        if move == OPPOSITE.get(current_direction):
            continue

        nxt = wrap(add(my_head, delta), w, h)

        if nxt in obstacles:
            continue

        score = 0

        # ==================================================
        # HARD SAFETY (HEAD KILL ZONE)
        # ==================================================

        if nxt in z1:
            continue

        # ==================================================
        # SURVIVAL SPACE
        # ==================================================

        space = flood_fill(nxt, obstacles, field_size)
        score += space * 12

        if space < 10:
            score -= 600  # trap detection

        # ==================================================
        # ESCAPE SAFETY (NEW)
        # ==================================================

        if not has_escape(nxt, obstacles | own_body, field_size):
            score -= 1000

        # ==================================================
        # ENEMY PRESSURE
        # ==================================================

        if nxt in z2:
            score -= 500
        if nxt in z3:
            score -= 200

        # ==================================================
        # BAD APPLES
        # ==================================================

        if nxt in bad_apples:
            score -= 300

        # ==================================================
        # APPLES (SAFE ONLY)
        # ==================================================

        if apples:
            safe_apples = [
                a for a in apples
                if not is_contested(a, my_head, snakes, field_size)
            ]

            target_list = safe_apples if safe_apples else apples

            nearest = min(wrap_dist(nxt, a, w, h) for a in target_list)
            score += max(0, 50 - nearest)

        # ==================================================
        # STARS (CONSERVATIVE)
        # ==================================================

        if stars:
            safe_stars = [
                s for s in stars
                if not is_contested(s, my_head, snakes, field_size)
            ]

            if safe_stars:
                d = min(wrap_dist(nxt, s, w, h) for s in safe_stars)
                if d <= 3:
                    score += 20 - d * 6

        # ==================================================
        # CENTER STABILITY
        # ==================================================

        center = (w // 2, h // 2)
        score -= wrap_dist(nxt, center, w, h) * 0.25

        score += emergency_escape_score(nxt, obstacles, field_size)

        # ==================================================
        # CONTINUITY
        # ==================================================

        if move == current_direction:
            score += 10

        if score > best_score:
            best_score = score
            best_move = move

    return best_move