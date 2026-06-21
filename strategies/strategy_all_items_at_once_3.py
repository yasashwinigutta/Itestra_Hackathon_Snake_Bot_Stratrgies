from collections import deque

# ==========================================================
# STABLE ALL-ITEMS FINALS STRATEGY
# ==========================================================
#
# This file intentionally keeps the same public entry point:
#
#     choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction)
#
# and returns ONLY a direction string, matching the uploaded strategyalls.py format.
# main2.py / api.py / Field.py / data_structures.py do not need changes.
#
# The strategy is conservative about death, strong on apple collection, and uses
# item knowledge for positioning. Direct item activation is not returned here
# because the current strategyalls.py format returns only a move.
# ==========================================================


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


# ==========================================================
# BASIC HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(pos, w, h):
    return (pos[0] % w, pos[1] % h)


def wrap_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


def neigh(pos, size):
    w, h = size
    for d in DIRECTIONS.values():
        yield wrap(add(pos, d), w, h)


def move_to_pos(my_head, target, size, current_direction=None):
    """Convert adjacent wrapped target position into direction."""
    w, h = size
    hx, hy = my_head

    options = {
        "NORTH": wrap((hx, hy - 1), w, h),
        "SOUTH": wrap((hx, hy + 1), w, h),
        "WEST": wrap((hx - 1, hy), w, h),
        "EAST": wrap((hx + 1, hy), w, h),
    }

    for d, p in options.items():
        if p == target and d != OPPOSITE.get(current_direction):
            return d
    return None


def norm_body(snake):
    return [tuple(p) for p in snake.get("body", []) if isinstance(p, (list, tuple)) and len(p) >= 2]


def is_alive_snake(snake):
    # If "alive" is not provided by main2.py, assume the snake is alive.
    return bool(snake.get("alive", True))


def text_has(words, text):
    t = str(text).lower()
    return any(w in t for w in words)


def snake_has(snake, names):
    """Checks inventory/effects fields defensively, without depending on exact API names."""
    inv = snake.get("inventory", []) or []
    eff = snake.get("active_effects", []) or snake.get("effects", []) or []

    for item in inv:
        if text_has(names, item):
            return True

    for e in eff:
        if isinstance(e, dict):
            if text_has(names, e.get("effect", "")) or text_has(names, e.get("kind", "")):
                return True
        else:
            if text_has(names, e):
                return True

    return False


def snake_effect_active(snake, names):
    """Stricter active-effect check. Inventory alone is not treated as active."""
    eff = snake.get("active_effects", []) or snake.get("effects", []) or []
    for e in eff:
        if isinstance(e, dict):
            if text_has(names, e.get("effect", "")) or text_has(names, e.get("kind", "")):
                if int(e.get("remaining_ticks", 1) or 1) > 0:
                    return True
        else:
            if text_has(names, e):
                return True
    return False


# ==========================================================
# ITEM CLASSIFICATION
# ==========================================================

def classify_items(items):
    apples, bad, stars, swords, boosts, stacks = [], [], [], [], [], []

    for it in items:
        kind = str(getattr(it, "kind", "")).lower()
        pos = tuple(getattr(it, "position", (0, 0)))

        if "bad" in kind:
            bad.append(pos)
        elif "apple" in kind:
            apples.append(pos)
        elif "star" in kind or "shield" in kind:
            stars.append(pos)
        elif "sword" in kind:
            swords.append(pos)
        elif "boost" in kind or "speed" in kind:
            boosts.append(pos)
        elif "stack" in kind:
            stacks.append(pos)

    return apples, bad, stars, swords, boosts, stacks


# ==========================================================
# FLOOD FILL / SPACE
# ==========================================================

def flood_fill(start, blocked, size, limit=700):
    if start in blocked:
        return 0

    q = deque([start])
    seen = {start}
    count = 0

    while q and count < limit:
        cur = q.popleft()
        count += 1

        for nxt in neigh(cur, size):
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)

    return count


def escape_count(pos, blocked, size):
    return sum(1 for n in neigh(pos, size) if n not in blocked)


def emergency_escape_score(pos, blocked, size):
    esc = escape_count(pos, blocked, size)
    if esc == 0:
        return -20000
    if esc == 1:
        return -7000
    if esc == 2:
        return -1500
    return esc * 150


# ==========================================================
# ENEMY PREDICTION
# ==========================================================

def enemy_prediction(snakes, my_head, size):
    """Predict live enemy head danger for 1, 2, and 3 ticks with torus movement."""
    z1, z2, z3 = set(), set(), set()
    r1, r2 = set(), set()
    sword_threat = set()

    for s in snakes:
        head = tuple(s.get("head", ()))
        if not head or head == my_head or not is_alive_snake(s):
            continue

        body = set(norm_body(s))
        speed_like = snake_has(s, ["speed", "boost"])
        sword_like = snake_has(s, ["sword"])

        # radius danger near current head
        for x in range(-2, 3):
            for y in range(-2, 3):
                p = wrap((head[0] + x, head[1] + y), *size)
                d = wrap_dist(head, p, *size)
                if d <= 1:
                    r1.add(p)
                if d <= 2:
                    r2.add(p)

        # possible future head cells
        frontier = {head}
        for depth in range(1, 4):
            new_frontier = set()
            for cur in frontier:
                # Normal one-cell movement.
                for n in neigh(cur, size):
                    # enemy normally won't move through its own body, but keep this soft:
                    if n in body and n != head:
                        continue
                    new_frontier.add(n)

                # If enemy may have speed/boost, also consider two-step reach in one tick.
                if speed_like and depth <= 2:
                    for n1 in neigh(cur, size):
                        for n2 in neigh(n1, size):
                            if n2 in body and n2 != head:
                                continue
                            new_frontier.add(n2)

            if depth == 1:
                z1.update(new_frontier)
            elif depth == 2:
                z2.update(new_frontier)
            else:
                z3.update(new_frontier)

            frontier = new_frontier

        if sword_like:
            # Sword threat is a halo around predicted head cells.
            for p in z1 | z2:
                sword_threat.add(p)
                sword_threat.update(neigh(p, size))

    return z1, z2, z3, r1, r2, sword_threat


# ==========================================================
# TARGET / CONTEST HELPERS
# ==========================================================

def is_contested(target, my_head, snakes, size, margin=0):
    my_d = wrap_dist(my_head, target, *size)

    for s in snakes:
        head = tuple(s.get("head", ()))
        if not head or head == my_head or not is_alive_snake(s):
            continue

        if wrap_dist(head, target, *size) <= my_d + margin:
            return True

    return False


def nearest_distance(pos, targets, size, default=999):
    if not targets:
        return default
    return min(wrap_dist(pos, t, *size) for t in targets)


def attraction_delta(my_head, nxt, targets, size):
    if not targets:
        return 0
    before = nearest_distance(my_head, targets, size)
    after = nearest_distance(nxt, targets, size)
    return before - after


def first_step_towards(start, targets, blocked, size, avoid=set()):
    """BFS first step toward any target, avoiding hard blocked and optionally danger cells."""
    if not targets:
        return None

    targets = set(targets)
    q = deque([start])
    seen = {start}
    parent = {}

    while q:
        cur = q.popleft()

        if cur in targets and cur != start:
            # backtrack to first step
            step = cur
            while parent.get(step) != start:
                step = parent[step]
            return step

        for n in neigh(cur, size):
            if n in seen or n in blocked or n in avoid:
                continue
            seen.add(n)
            parent[n] = cur
            q.append(n)

    return None


# ==========================================================
# BODY / OBSTACLE MODEL
# ==========================================================

def build_body_sets(my_head, snakes, raw_obstacles):
    my_snake = next((s for s in snakes if tuple(s.get("head", ())) == my_head), None)
    own_body = set(norm_body(my_snake)) if my_snake else set()

    dead_bodies = set()
    live_heads = set()
    live_enemy_bodies = set()
    live_enemy_body_no_head = set()

    for s in snakes:
        body = set(norm_body(s))
        head = tuple(s.get("head", ())) if s.get("head") is not None else None

        if not body:
            continue

        if head == my_head:
            continue

        if not is_alive_snake(s):
            dead_bodies.update(body)
        else:
            if head:
                live_heads.add(head)
            live_enemy_bodies.update(body)
            live_enemy_body_no_head.update(p for p in body if p != head)

    raw_obstacles = set(raw_obstacles or [])

    # Anything in raw obstacles that is not live body is treated as hard.
    # This preserves dead/corpse obstacles while not blindly hard-blocking
    # all live bodies when sword/star logic could matter.
    hard_static = raw_obstacles - live_enemy_bodies

    return {
        "my_snake": my_snake,
        "own_body": own_body,
        "dead_bodies": dead_bodies,
        "live_heads": live_heads,
        "live_enemy_bodies": live_enemy_bodies,
        "live_enemy_body_no_head": live_enemy_body_no_head,
        "hard_static": hard_static,
    }


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
    size = field_size

    my_head = tuple(my_head)

    apples, bad_apples, stars, swords, boosts, stacks = classify_items(items)

    bodies = build_body_sets(my_head, snakes, obstacles)
    my_snake = bodies["my_snake"]
    own_body = bodies["own_body"]
    dead_bodies = bodies["dead_bodies"]
    live_heads = bodies["live_heads"]
    live_enemy_bodies = bodies["live_enemy_bodies"]
    live_enemy_body_no_head = bodies["live_enemy_body_no_head"]
    hard_static = bodies["hard_static"]

    has_sword_item = snake_has(my_snake or {}, ["sword"])
    sword_active = snake_effect_active(my_snake or {}, ["sword"])
    has_stack_item = snake_has(my_snake or {}, ["stack"])
    speed_active = snake_effect_active(my_snake or {}, ["speed", "boost"])
    star_active = snake_effect_active(my_snake or {}, ["star", "shield"])

    z1, z2, z3, r1, r2, sword_threat = enemy_prediction(snakes, my_head, size)

    # Own body and dead/corpse bodies are hard. Live bodies are handled separately:
    # generally blocked, but body segments can become attack targets if sword is active/available.
    hard_blocked = set(hard_static) | set(own_body) | set(dead_bodies)

    # Try to be slightly less scared of our own tail if the snake is moving normally.
    # But do NOT remove dead bodies or enemy bodies from hard safety.
    if len(own_body) > 2:
        tail = next(iter(own_body), None)
        # Do not depend on body order too much; if my_snake body exists, first segment is usually tail.
        body_list = norm_body(my_snake) if my_snake else []
        if body_list:
            hard_blocked.discard(body_list[-1] if body_list[0] == my_head else body_list[0])

    # For flood-fill survival, live enemy bodies are also blocked unless we are star/sword active.
    survival_blocked = set(hard_blocked) | live_heads
    if not (sword_active or star_active):
        survival_blocked |= live_enemy_bodies

    # Normal legal movement blocks live heads always. Live body is blocked unless we can attack/pass.
    can_touch_live_body = sword_active or star_active
    can_prepare_sword = has_sword_item

    moves = {}
    for move, delta in DIRECTIONS.items():
        if move == OPPOSITE.get(current_direction):
            continue
        first = wrap(add(my_head, delta), w, h)
        path = [first]

        if speed_active:
            # If speed is currently active, movement may cover 2 cells.
            second = wrap(add(first, delta), w, h)
            path.append(second)

        moves[move] = path

    # ------------------------------------------------------
    # Emergency Stack positioning:
    # Cannot activate directly with this return format, so choose moves that
    # collect Stack / preserve open space when body exposure is high.
    # ------------------------------------------------------

    body_exposure = 0
    if own_body:
        for p in own_body:
            if p in sword_threat or p in z1 or p in z2:
                body_exposure += 1

    crowded = any(wrap_dist(my_head, eh, w, h) <= 4 for eh in live_heads)
    stack_needed = has_stack_item and (body_exposure >= 2 or crowded)

    # ------------------------------------------------------
    # Immediate adjacent apple / sword opportunities
    # ------------------------------------------------------

    best_move = None
    best_score = -10**18

    for move, path in moves.items():
        nxt = path[-1]
        first = path[0]

        # ---------------- HARD BLOCKS ----------------
        # own body, dead bodies, static/corpse obstacles.
        if any(p in hard_blocked for p in path):
            continue

        # enemy head zone: never move into live head directly.
        if any(p in live_heads for p in path):
            continue

        # live body: normally blocked. If sword/star active, allow body segment contact.
        body_contact = any(p in live_enemy_body_no_head for p in path)
        if body_contact and not can_touch_live_body:
            # If sword is merely in inventory, do not actually crash into body because
            # this strategy return format cannot activate it. Instead score toward it later.
            continue

        # enemy immediate head predictions
        if any(p in z1 or p in r1 for p in path):
            # Direct head-crash danger is not worth apple/item greed.
            continue

        # ---------------- BASE SCORE ----------------
        score = 0

        # Space/endurance: use stricter blocked model.
        space = flood_fill(nxt, survival_blocked, size)
        score += space * 10

        if space < 12:
            score -= 2500
        elif space < 25:
            score -= 700

        score += emergency_escape_score(nxt, survival_blocked, size)

        # ---------------- ENEMY DANGER ----------------
        if nxt in z2:
            score -= 900
        if nxt in r2:
            score -= 650
        if nxt in z3:
            score -= 250
        if nxt in sword_threat:
            score -= 900

        # Keep distance from enemy heads.
        for eh in live_heads:
            d = wrap_dist(nxt, eh, w, h)
            if d <= 1:
                score -= 3000
            elif d == 2:
                score -= 700
            elif d == 3:
                score -= 120

        # ---------------- BAD APPLES ----------------
        bad_hits = sum(1 for p in path if p in bad_apples)
        score -= bad_hits * 1300

        # Penalize proximity to bad apples, but do not overdo it.
        if bad_apples:
            bd = nearest_distance(nxt, bad_apples, size)
            if bd == 1:
                score -= 140
            elif bd == 2:
                score -= 45

        # ---------------- GOOD APPLES ----------------
        if apples:
            # Adjacent safe apple is valuable.
            if nxt in apples:
                score += 1900

            safe_apples = [
                a for a in apples
                if a not in dead_bodies
                and a not in hard_blocked
                and a not in z1
                and not is_contested(a, my_head, snakes, size, margin=0)
            ]
            target_apples = safe_apples if safe_apples else apples

            score += max(0, 90 - nearest_distance(nxt, target_apples, size) * 9)
            score += attraction_delta(my_head, nxt, target_apples, size) * 120

        # ---------------- SWORD ITEMS / ATTACK POSITIONING ----------------
        if swords:
            uncontested_swords = [s for s in swords if not is_contested(s, my_head, snakes, size, margin=0)]
            target_swords = uncontested_swords if uncontested_swords else swords
            score += max(0, 80 - nearest_distance(nxt, target_swords, size) * 8)
            score += attraction_delta(my_head, nxt, target_swords, size) * 95

        # If sword is active, cutting live body is very high value.
        if body_contact and sword_active:
            score += 8000

        # If sword is available but not active, move near cuttable body safely, but do not collide.
        if has_sword_item or sword_active:
            cut_candidates = []
            for s in snakes:
                if tuple(s.get("head", ())) == my_head or not is_alive_snake(s):
                    continue
                body = norm_body(s)
                # prefer front/middle segments over tail; avoid head.
                for idx, seg in enumerate(body[1:], start=1):
                    # Skip very tail-like last segment if possible.
                    preference = max(0, len(body) - idx)
                    if seg in dead_bodies:
                        continue
                    if seg in live_heads:
                        continue
                    cut_candidates.append((seg, preference))

            if cut_candidates:
                # Move adjacent/toward valuable cut candidates without entering body unless sword active.
                best_cut_gain = 0
                for seg, pref in cut_candidates:
                    d_now = wrap_dist(my_head, seg, w, h)
                    d_next = wrap_dist(nxt, seg, w, h)
                    gain = (d_now - d_next) * 240 + pref * 6
                    if d_next == 1:
                        gain += 850
                    if d_next == 2:
                        gain += 280
                    best_cut_gain = max(best_cut_gain, gain)
                score += best_cut_gain

        # ---------------- STACK ITEMS / DEFENSE ----------------
        if stacks:
            safe_stacks = [s for s in stacks if s not in hard_blocked and s not in z1]
            if safe_stacks:
                urgency = 2.2 if stack_needed else 1.0
                score += urgency * max(0, 80 - nearest_distance(nxt, safe_stacks, size) * 8)
                score += urgency * attraction_delta(my_head, nxt, safe_stacks, size) * 100

        if stack_needed:
            # Prefer moves that increase space and get out of predicted body-exposure zones.
            score += 800
            if nxt in sword_threat or nxt in z2:
                score -= 900

        # ---------------- BOOST/SPEED ITEMS ----------------
        if boosts:
            safe_boosts = [b for b in boosts if b not in hard_blocked and b not in z1]
            if safe_boosts:
                score += max(0, 55 - nearest_distance(nxt, safe_boosts, size) * 7)
                # In danger, boost pickup can be very useful.
                if crowded or space < 30:
                    score += attraction_delta(my_head, nxt, safe_boosts, size) * 80

        # ---------------- STAR ----------------
        if stars:
            safe_stars = []
            for s in stars:
                if s in hard_blocked or s in z1:
                    continue
                # Star only if we are clearly ahead; otherwise keep farming.
                if not is_contested(s, my_head, snakes, size, margin=0):
                    safe_stars.append(s)

            if safe_stars:
                d_star = nearest_distance(nxt, safe_stars, size)
                # Medium-high priority, but below immediate safe apple/sword.
                if d_star <= 4:
                    score += max(0, 300 - d_star * 55)
                score += attraction_delta(my_head, nxt, safe_stars, size) * 70

        if star_active:
            # Use shield for bolder apple/item positioning, but do not chase tags far away.
            score += 150
            for eh in live_heads:
                if wrap_dist(nxt, eh, w, h) == 1:
                    score += 120  # small opportunistic pressure only

        # ---------------- CONTINUITY / ANTI-LOOP ----------------
        if move == current_direction:
            score += 45

        if hasattr(choose_next_move, "prev") and nxt == choose_next_move.prev:
            score -= 120

        # Slight center bias only when there are no apple targets, avoids aimless wall orbit.
        if not apples:
            center = (w // 2, h // 2)
            score -= wrap_dist(nxt, center, w, h) * 0.12

        if score > best_score:
            best_score = score
            best_move = move

    choose_next_move.prev = my_head

    if best_move:
        return best_move

    # ======================================================
    # EMERGENCY FALLBACK:
    # Never blindly continue into own/dead body. Choose least terrible move.
    # ======================================================

    fallback_move = None
    fallback_score = -10**18

    for move, delta in DIRECTIONS.items():
        if move == OPPOSITE.get(current_direction):
            continue

        nxt = wrap(add(my_head, delta), w, h)
        path = [nxt]

        if any(p in hard_blocked for p in path):
            continue
        if any(p in live_heads for p in path):
            continue

        score = flood_fill(nxt, hard_blocked | live_heads | dead_bodies, size) * 5
        if nxt in z1 or nxt in r1:
            score -= 10000
        if nxt in bad_apples:
            score -= 800
        if score > fallback_score:
            fallback_score = score
            fallback_move = move

    if fallback_move:
        return fallback_move

    # Last resort: return a non-reverse direction if possible.
    for move in DIRECTIONS:
        if move != OPPOSITE.get(current_direction):
            return move

    return current_direction
