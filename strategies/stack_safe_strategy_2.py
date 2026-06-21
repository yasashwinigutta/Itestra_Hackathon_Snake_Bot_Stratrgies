from collections import deque

# ==========================================================
# STACK-SAFE COMBAT SURVIVAL STRATEGY
# ==========================================================
# Entry point preserved:
# choose_next_move(my_head, obstacles, snakes, size, items, direction)
# returns: (best_direction, optional_activation_string)
#
# Important: this strategy may return "STACK" when stack should be used.
# The caller/main action handler must pass that string to api.activate_item().

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

# Tunable weights
HEAD_DANGER_1_PENALTY = 900
HEAD_DANGER_2_PENALTY = 320
HEAD_DANGER_3_PENALTY = 120
SWORD_THREAT_PENALTY = 850
SPEED_THREAT_PENALTY = 500
BOOSTED_CONTACT_PENALTY = 180
BAD_APPLE_PENALTY = 260
GOOD_APPLE_REWARD = 260
VALUABLE_ITEM_REWARD = 220
OPEN_SPACE_WEIGHT = 8
STRAIGHT_BONUS = 18
STACK_THREAT_THRESHOLD = 950
STACK_COOLDOWN_TICKS = 5
SWORD_COOLDOWN_TICKS = 5
BOOST_COOLDOWN_TICKS = 4

# ==========================================================
# BASIC HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(p, w, h):
    return (p[0] % w, p[1] % h)


def dist(a, b, w, h):
    return min(abs(a[0] - b[0]), w - abs(a[0] - b[0])) + \
           min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))


def neighbors(pos, w, h):
    return [wrap(add(pos, d), w, h) for d in DIRECTIONS.values()]


def move_from_step(head, step, w, h):
    for move, delta in DIRECTIONS.items():
        if wrap(add(head, delta), w, h) == step:
            return move
    return None


def flood_fill(start, blocked, size, limit=450):
    if start in blocked:
        return 0
    w, h = size
    q = deque([start])
    seen = {start}
    count = 0
    while q and count < limit:
        cur = q.popleft()
        count += 1
        for nxt in neighbors(cur, w, h):
            if nxt in blocked or nxt in seen:
                continue
            seen.add(nxt)
            q.append(nxt)
    return count


def escape_options(pos, blocked, size):
    w, h = size
    return sum(1 for nxt in neighbors(pos, w, h) if nxt not in blocked)


def has_keyword(values, *keywords):
    text = " ".join(str(v).lower() for v in values)
    return any(k.lower() in text for k in keywords)


def snake_has_item_or_effect(snake, *keywords):
    inv = snake.get("inventory", []) or []
    effects = snake.get("active_effects", []) or []
    return has_keyword(inv, *keywords) or has_keyword(effects, *keywords)


def is_boosted(snake):
    return snake_has_item_or_effect(snake, "star", "boost", "shield")


def has_sword(snake):
    return snake_has_item_or_effect(snake, "sword")


def has_speed(snake):
    return snake_has_item_or_effect(snake, "speed", "boost")


def classify_items(items):
    apples, bad, swords, boosts, stars, speeds, stacks = [], [], [], [], [], [], []
    for it in items:
        kind = str(getattr(it, "kind", "")).lower()
        pos = getattr(it, "position", None)
        if pos is None:
            continue
        pos = (int(pos[0]), int(pos[1]))

        if "bad" in kind:
            bad.append(pos)
        elif "apple" in kind:
            apples.append(pos)
        elif "sword" in kind:
            swords.append(pos)
        elif "stack" in kind:
            stacks.append(pos)
        elif "speed" in kind:
            speeds.append(pos)
        elif "star" in kind or "shield" in kind:
            stars.append(pos)
        elif "boost" in kind:
            boosts.append(pos)
    return apples, bad, swords, boosts, stars, speeds, stacks


# ==========================================================
# PATHING
# ==========================================================

def first_step_to_target(start, target, blocked, size, avoid=None, soft_bad=None):
    """BFS on torus. Returns first step toward target.

    blocked: impossible cells.
    avoid: high-risk cells to avoid if possible.
    soft_bad: bad-apple cells; allowed, but explored after normal cells.
    """
    avoid = avoid or set()
    soft_bad = soft_bad or set()
    if start == target:
        return None

    w, h = size
    q = deque([start])
    came = {start: None}

    while q:
        cur = q.popleft()
        if cur == target:
            break

        normal_next = []
        risky_next = []
        bad_next = []
        for nxt in neighbors(cur, w, h):
            if nxt in blocked or nxt in came:
                continue
            if nxt in soft_bad:
                bad_next.append(nxt)
            elif nxt in avoid:
                risky_next.append(nxt)
            else:
                normal_next.append(nxt)

        for nxt in normal_next + bad_next + risky_next:
            came[nxt] = cur
            q.append(nxt)

    if target not in came:
        return None

    cur = target
    while came[cur] is not None and came[cur] != start:
        cur = came[cur]
    return cur


# ==========================================================
# ENEMY PREDICTION
# ==========================================================

def reachable_cells_from(head, body, size, depth=2, speed_active=False):
    """Predict possible enemy positions up to depth ticks.

    If speed is active, enemy may effectively cover two cells in one tick.
    We return all intermediate/reachable cells as dangerous.
    """
    w, h = size
    body_set = set(body)
    zones_by_depth = {i: set() for i in range(1, depth + 1)}
    frontier = {head}

    for step in range(1, depth + 1):
        next_frontier = set()
        for pos in frontier:
            step_cells = neighbors(pos, w, h)

            if speed_active:
                expanded = set(step_cells)
                for p in step_cells:
                    expanded.update(neighbors(p, w, h))
                step_cells = list(expanded)

            for nxt in step_cells:
                # Enemy usually cannot move through its own body, but keep head prediction flexible.
                if nxt in body_set and nxt != head:
                    continue
                zones_by_depth[step].add(nxt)
                next_frontier.add(nxt)
        frontier = next_frontier or frontier

    return zones_by_depth


def build_enemy_maps(my_head, snakes, size):
    w, h = size
    enemy_heads = []
    enemy_bodies = set()
    head_radius_1 = set()
    head_radius_2 = set()
    danger_1 = set()
    danger_2 = set()
    danger_3 = set()
    sword_threat = set()
    speed_threat = set()
    boosted_threat = set()

    for s in snakes:
        if s.get("head") == my_head:
            continue
        body = list(s.get("body", []))
        if not body:
            continue
        head = s.get("head", body[0])
        enemy_heads.append(head)
        enemy_bodies.update(body)

        for x in range(w):
            # Avoid full grid scan in huge maps by using local offsets below instead.
            pass

        # Radius zones around enemy head using torus offsets up to 2.
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                p = wrap((head[0] + dx, head[1] + dy), w, h)
                d = dist(head, p, w, h)
                if d <= 1:
                    head_radius_1.add(p)
                if d <= 2:
                    head_radius_2.add(p)

        speed = has_speed(s)
        sword = has_sword(s)
        boosted = is_boosted(s)
        pred = reachable_cells_from(head, body, size, depth=3, speed_active=speed)

        danger_1.update(pred[1])
        danger_2.update(pred[2])
        danger_3.update(pred[3])

        if speed:
            speed_threat.update(pred[1] | pred[2])
        if boosted:
            boosted_threat.update(pred[1] | pred[2] | set(body))
        if sword:
            # Sword threat includes enemy reachable cells and adjacent cells around them.
            for p in pred[1] | pred[2]:
                sword_threat.add(p)
                sword_threat.update(neighbors(p, w, h))

    return {
        "enemy_heads": enemy_heads,
        "enemy_bodies": enemy_bodies,
        "head_radius_1": head_radius_1,
        "head_radius_2": head_radius_2,
        "danger_1": danger_1,
        "danger_2": danger_2,
        "danger_3": danger_3,
        "sword_threat": sword_threat,
        "speed_threat": speed_threat,
        "boosted_threat": boosted_threat,
    }


def body_exposure_score(my_body, enemy_maps):
    if not my_body:
        return 0
    exposure = 0
    body_set = set(my_body)
    exposure += 900 * len(body_set & enemy_maps["sword_threat"])
    exposure += 450 * len(body_set & enemy_maps["speed_threat"])
    exposure += 300 * len(body_set & enemy_maps["danger_1"])
    exposure += 120 * len(body_set & enemy_maps["danger_2"])
    exposure += 120 * len(body_set & enemy_maps["boosted_threat"])
    return exposure


def should_activate_stack(my_body, my_head, inventory, enemy_maps, size, chosen_pos=None):
    if not has_keyword(inventory, "stack"):
        return False

    if not my_body:
        return False

    exposure = body_exposure_score(my_body, enemy_maps)
    immediate_body_contact = bool(set(my_body) & enemy_maps["danger_1"])
    sword_can_cut = bool(set(my_body) & enemy_maps["sword_threat"])
    speed_can_touch = bool(set(my_body) & enemy_maps["speed_threat"])
    boosted_can_farm = bool(set(my_body) & enemy_maps["boosted_threat"])

    crowded_heads = sum(
        1 for hpos in enemy_maps["enemy_heads"]
        if dist(my_head, hpos, size[0], size[1]) <= 3
    )

    chosen_risky = False
    if chosen_pos is not None:
        chosen_risky = (
            chosen_pos in enemy_maps["danger_1"] or
            chosen_pos in enemy_maps["sword_threat"] or
            chosen_pos in enemy_maps["speed_threat"]
        )

    return (
        sword_can_cut or
        speed_can_touch or
        immediate_body_contact or
        boosted_can_farm or
        exposure >= STACK_THREAT_THRESHOLD or
        crowded_heads >= 2 or
        chosen_risky
    )


# ==========================================================
# SCORING HELPERS
# ==========================================================

def cell_risk_score(pos, enemy_maps):
    risk = 0
    if pos in enemy_maps["danger_1"]:
        risk += HEAD_DANGER_1_PENALTY
    if pos in enemy_maps["danger_2"]:
        risk += HEAD_DANGER_2_PENALTY
    if pos in enemy_maps["danger_3"]:
        risk += HEAD_DANGER_3_PENALTY
    if pos in enemy_maps["head_radius_1"]:
        risk += HEAD_DANGER_1_PENALTY
    elif pos in enemy_maps["head_radius_2"]:
        risk += HEAD_DANGER_2_PENALTY
    if pos in enemy_maps["sword_threat"]:
        risk += SWORD_THREAT_PENALTY
    if pos in enemy_maps["speed_threat"]:
        risk += SPEED_THREAT_PENALTY
    if pos in enemy_maps["boosted_threat"]:
        risk += BOOSTED_CONTACT_PENALTY
    return risk


def nearest_distance(pos, targets, size):
    if not targets:
        return None
    w, h = size
    return min(dist(pos, t, w, h) for t in targets)


def immediate_cut_move(my_head, snakes, size):
    """If our sword is active/available, find adjacent enemy body segment to cut."""
    w, h = size
    for move, delta in DIRECTIONS.items():
        nxt = wrap(add(my_head, delta), w, h)
        for s in snakes:
            if s.get("head") == my_head:
                continue
            body = list(s.get("body", []))
            # Prefer cutting body, not head collision.
            if nxt in body[1:]:
                return move
    return None


def best_target_step(my_head, targets, blocked, size, enemy_maps, bad_apples=None):
    if not targets:
        return None
    w, h = size
    bad_apples = set(bad_apples or [])

    ranked = sorted(
        targets,
        key=lambda t: (
            dist(my_head, t, w, h),
            cell_risk_score(t, enemy_maps),
        )
    )

    avoid = enemy_maps["danger_1"] | enemy_maps["head_radius_1"] | enemy_maps["sword_threat"]
    for target in ranked[:8]:
        step = first_step_to_target(my_head, target, blocked, size, avoid=avoid, soft_bad=bad_apples)
        if step is None:
            continue
        if step in blocked:
            continue
        return step
    return None


# ==========================================================
# STATE
# ==========================================================

_tick = 0
_last_boost = -100
_last_sword = -100
_last_stack = -100


# ==========================================================
# MAIN STRATEGY
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, size, items, direction):
    global _tick, _last_boost, _last_sword, _last_stack
    _tick += 1

    w, h = size
    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = list(my_snake.get("body", [])) if my_snake else [my_head]
    my_body_set = set(my_body)
    my_body_no_head = set(my_body[1:]) if len(my_body) > 1 else set()
    inventory = list(my_snake.get("inventory", [])) if my_snake else []

    apples, bad_apples, swords, boosts, stars, speeds, stacks = classify_items(items)

    # Block true collisions. Bad apples are not blocked; they are penalized.
    enemy_maps = build_enemy_maps(my_head, snakes, size)
    enemy_bodies = enemy_maps["enemy_bodies"]
    blocked = (set(obstacles) | my_body_no_head | enemy_bodies) - {my_head}

    has_stack_item = has_keyword(inventory, "stack")
    has_sword_item = has_keyword(inventory, "sword")
    has_boost_item = has_keyword(inventory, "boost", "speed")
    my_boosted = my_snake is not None and is_boosted(my_snake)

    legal_moves = {}
    emergency_moves = {}
    for move, delta in DIRECTIONS.items():
        if move == OPPOSITE.get(direction):
            continue
        nxt = wrap(add(my_head, delta), w, h)
        if nxt in my_body_no_head:
            continue
        if nxt in enemy_bodies and not (my_boosted or has_sword_item):
            continue
        # Main safe set avoids immediate head danger. Emergency set may allow it if no choice.
        if nxt not in enemy_maps["danger_1"] and nxt not in enemy_maps["head_radius_1"]:
            legal_moves[move] = nxt
        emergency_moves[move] = nxt

    moves_to_score = legal_moves if legal_moves else emergency_moves
    if not moves_to_score:
        return direction, None

    # ------------------------------------------------------
    # Immediate sword cut if available and not suicidal.
    # ------------------------------------------------------
    cut_move = immediate_cut_move(my_head, snakes, size) if has_sword_item else None
    if cut_move in moves_to_score:
        cut_pos = moves_to_score[cut_move]
        if cell_risk_score(cut_pos, enemy_maps) < HEAD_DANGER_1_PENALTY:
            activate = "SWORD" if _tick - _last_sword >= SWORD_COOLDOWN_TICKS else None
            if activate:
                _last_sword = _tick
            return cut_move, activate

    # ------------------------------------------------------
    # Target selection: nearby safe apples/items, but never tunnel into head danger.
    # ------------------------------------------------------
    valuable_items = swords + stacks + boosts + speeds + stars
    target_step = None

    # Adjacent good apple: take it if safe.
    for move, pos in moves_to_score.items():
        if pos in apples and cell_risk_score(pos, enemy_maps) < HEAD_DANGER_1_PENALTY:
            target_step = pos
            break

    # Otherwise path to valuable item under pressure, then apples.
    if target_step is None and (valuable_items or apples):
        if body_exposure_score(my_body, enemy_maps) > 400 and stacks:
            target_step = best_target_step(my_head, stacks, blocked, size, enemy_maps, bad_apples)
        if target_step is None and valuable_items:
            target_step = best_target_step(my_head, valuable_items, blocked, size, enemy_maps, bad_apples)
        if target_step is None and apples:
            target_step = best_target_step(my_head, apples, blocked, size, enemy_maps, bad_apples)

    preferred_move = move_from_step(my_head, target_step, w, h) if target_step else None

    # ------------------------------------------------------
    # Score all moves.
    # ------------------------------------------------------
    best_move = direction if direction in moves_to_score else next(iter(moves_to_score))
    best_score = -10**18

    nearest_enemy = None
    if enemy_maps["enemy_heads"]:
        nearest_enemy = min(enemy_maps["enemy_heads"], key=lambda p: dist(my_head, p, w, h))

    for move, pos in moves_to_score.items():
        score = 0

        # Open space / endurance.
        space = flood_fill(pos, blocked, size)
        score += space * OPEN_SPACE_WEIGHT
        score += escape_options(pos, blocked, size) * 35
        if escape_options(pos, blocked, size) <= 1:
            score -= 650

        # Safety first: enemy heads, sword, speed, boosted pressure.
        score -= cell_risk_score(pos, enemy_maps)

        # Body exposure after this move: approximate by shifting head into body.
        future_body = [pos] + my_body[:-1]
        score -= min(1600, body_exposure_score(future_body, enemy_maps) * 0.35)

        # Apples and bad apples.
        if pos in apples:
            score += GOOD_APPLE_REWARD
        if pos in bad_apples:
            score -= BAD_APPLE_PENALTY

        nd = nearest_distance(pos, apples, size)
        if nd is not None:
            score += 180 / (nd + 1)

        bd = nearest_distance(pos, bad_apples, size)
        if bd is not None:
            score -= 80 / (bd + 1)

        # Valuable items.
        if pos in swords:
            score += VALUABLE_ITEM_REWARD + 120
        if pos in stacks:
            score += VALUABLE_ITEM_REWARD + 160
        if pos in boosts or pos in speeds:
            score += VALUABLE_ITEM_REWARD
        if pos in stars:
            score += VALUABLE_ITEM_REWARD

        # Prefer the chosen path target, but not more than survival.
        if preferred_move == move:
            score += 180

        # Sword offense: near enemy body is good only if sword is available.
        if has_sword_item:
            for s in snakes:
                if s.get("head") == my_head:
                    continue
                body = list(s.get("body", []))
                if any(dist(pos, b, w, h) <= 1 for b in body[1:]):
                    score += 180
        else:
            # Without sword, don't brush bodies too much.
            if any(dist(pos, b, w, h) == 1 for b in enemy_bodies):
                score -= 60

        # Keep distance from nearest head unless attacking safely.
        if nearest_enemy:
            d_enemy = dist(pos, nearest_enemy, w, h)
            if d_enemy <= 1:
                score -= 800
            elif d_enemy == 2:
                score -= 260
            else:
                score += min(d_enemy, 8) * 6

        if move == direction:
            score += STRAIGHT_BONUS

        if score > best_score:
            best_score = score
            best_move = move

    chosen_pos = moves_to_score.get(best_move, wrap(add(my_head, DIRECTIONS.get(best_move, (0, 0))), w, h))

    # ------------------------------------------------------
    # Activation decision. Defense beats offense.
    # ------------------------------------------------------
    activate = None

    if has_stack_item and _tick - _last_stack >= STACK_COOLDOWN_TICKS:
        if should_activate_stack(my_body, my_head, inventory, enemy_maps, size, chosen_pos):
            activate = "STACK"
            _last_stack = _tick

    # Use boost/speed to escape pressure if stack is not used.
    if activate is None and has_boost_item and _tick - _last_boost >= BOOST_COOLDOWN_TICKS:
        if cell_risk_score(chosen_pos, enemy_maps) > 450 or body_exposure_score(my_body, enemy_maps) > 700:
            activate = "BOOST"
            _last_boost = _tick

    # Use sword when a cut is adjacent or when an enemy is close enough for a real fight.
    if activate is None and has_sword_item and _tick - _last_sword >= SWORD_COOLDOWN_TICKS:
        if cut_move == best_move or any(dist(my_head, hpos, w, h) <= 3 for hpos in enemy_maps["enemy_heads"]):
            activate = "SWORD"
            _last_sword = _tick

    return best_move, activate
