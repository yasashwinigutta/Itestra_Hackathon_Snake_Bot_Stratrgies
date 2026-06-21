from collections import deque

# ==========================================================
# CORE MOVES
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

# Small memory/cooldowns. main_final.py calls this module repeatedly.
_tick = 0
_last_boost = -100
_last_sword = -100
_last_stack = -100
_prev_positions = deque(maxlen=8)


# ==========================================================
# BASIC GRID HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(pos, w, h):
    return (pos[0] % w, pos[1] % h)


def wrap_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


def neighbors(pos, w, h):
    return [wrap(add(pos, d), w, h) for d in DIRECTIONS.values()]


def step_for_move(pos, move, size):
    w, h = size
    return wrap(add(pos, DIRECTIONS[move]), w, h)


def move_from_step(head, step, size):
    w, h = size
    for move, delta in DIRECTIONS.items():
        if wrap(add(head, delta), w, h) == step:
            return move
    return None


def legal_direction_names(current_direction):
    forbidden = OPPOSITE.get(current_direction)
    return [m for m in DIRECTIONS if m != forbidden]


# ==========================================================
# ITEM / EFFECT HELPERS
# ==========================================================

def _text_blob(obj):
    """Accept either a snake dict, inventory list, effect list, or raw string."""
    if obj is None:
        return ""
    if isinstance(obj, dict):
        inv = obj.get("inventory", []) or []
        eff = obj.get("active_effects", []) or []
        return " ".join(map(str, inv + eff)).lower()
    if isinstance(obj, (list, tuple, set)):
        return " ".join(map(str, obj)).lower()
    return str(obj).lower()


def has_keyword(obj, *keywords):
    text = _text_blob(obj)
    return any(k.lower() in text for k in keywords)


def has_sword(snake_or_inv):
    return has_keyword(snake_or_inv, "sword")


def has_stack(snake_or_inv):
    return has_keyword(snake_or_inv, "stack")


def has_boost(snake_or_inv):
    return has_keyword(snake_or_inv, "boost", "speed")


def has_star(snake_or_inv):
    return has_keyword(snake_or_inv, "star", "shield")


def classify_items(items):
    apples, bad, swords = [], [], []
    boosts, stars, speeds, stacks = [], [], [], []

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
# SURVIVAL / FLOOD FILL
# ==========================================================

def flood_fill(start, blocked, size, limit=700):
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
    return sum(1 for n in neighbors(pos, w, h) if n not in blocked)


def nearest_distance(pos, targets, size):
    if not targets:
        return None
    w, h = size
    return min(wrap_dist(pos, t, w, h) for t in targets)


def is_contested(target, my_head, snakes, size, margin=0):
    """True if an enemy reaches target as fast or faster."""
    w, h = size
    my_d = wrap_dist(my_head, target, w, h)
    for s in snakes:
        if s.get("head") == my_head:
            continue
        if wrap_dist(s.get("head"), target, w, h) <= my_d + margin:
            return True
    return False


# ==========================================================
# ENEMY PREDICTION
# ==========================================================

def build_enemy_maps(my_head, snakes, size):
    w, h = size

    enemy_heads = set()
    enemy_bodies = set()
    enemy_body_no_heads = set()

    danger_1, danger_2, danger_3 = set(), set(), set()
    sword_threat, boost_threat, star_threat = set(), set(), set()

    for s in snakes:
        head = s.get("head")
        body = list(s.get("body", []))
        if not head or not body or head == my_head:
            continue

        enemy_heads.add(head)
        enemy_bodies.update(body)
        enemy_body_no_heads.update(body[1:])

        # 1-step head danger
        first = set(neighbors(head, w, h))
        danger_1.update(first)
        danger_1.add(head)

        # 2/3-step approximate reachable zones
        second = set()
        for p in first:
            second.update(neighbors(p, w, h))
        danger_2.update(second)

        third = set()
        for p in second:
            third.update(neighbors(p, w, h))
        danger_3.update(third)

        if has_boost(s):
            for p in first:
                boost_threat.add(p)
                boost_threat.update(neighbors(p, w, h))

        if has_sword(s):
            # If enemy has sword, protect our path around enemy head and nearby body.
            sword_threat.update(first)
            sword_threat.update(second)
            for b in body:
                if wrap_dist(head, b, w, h) <= 4:
                    sword_threat.add(b)
                    sword_threat.update(neighbors(b, w, h))

        if has_star(s):
            star_threat.update(first)
            star_threat.update(second)
            star_threat.update(body)

    return {
        "enemy_heads": enemy_heads,
        "enemy_bodies": enemy_bodies,
        "enemy_body_no_heads": enemy_body_no_heads,
        "danger_1": danger_1,
        "danger_2": danger_2,
        "danger_3": danger_3,
        "sword_threat": sword_threat,
        "boost_threat": boost_threat,
        "star_threat": star_threat,
    }


def cell_risk_score(pos, enemy_maps):
    risk = 0
    if pos in enemy_maps["enemy_heads"]:
        risk += 100000
    if pos in enemy_maps["danger_1"]:
        risk += 4000
    if pos in enemy_maps["danger_2"]:
        risk += 900
    if pos in enemy_maps["danger_3"]:
        risk += 250
    if pos in enemy_maps["sword_threat"]:
        risk += 850
    if pos in enemy_maps["boost_threat"]:
        risk += 550
    if pos in enemy_maps["star_threat"]:
        risk += 350
    return risk


def body_exposure_score(my_body, enemy_maps):
    if not my_body:
        return 0
    body_set = set(my_body)
    exposure = 0
    exposure += 1400 * len(body_set & enemy_maps["sword_threat"])
    exposure += 800 * len(body_set & enemy_maps["boost_threat"])
    exposure += 550 * len(body_set & enemy_maps["danger_1"])
    exposure += 250 * len(body_set & enemy_maps["danger_2"])
    exposure += 180 * len(body_set & enemy_maps["star_threat"])
    return exposure


# ==========================================================
# PATHFINDING
# ==========================================================

def bfs_first_step(start, targets, blocked, enemy_maps, size, avoid_bad=None, max_depth=80):
    """Risk-aware torus BFS. Returns first step toward any target."""
    if not targets:
        return None
    targets = set(targets)
    avoid_bad = set(avoid_bad or [])
    w, h = size

    q = deque([start])
    parent = {start: None}
    depth = {start: 0}

    best = None
    best_key = None

    while q:
        cur = q.popleft()
        d = depth[cur]

        if cur in targets and cur != start:
            key = (
                d,
                cell_risk_score(cur, enemy_maps),
                1 if cur in avoid_bad else 0,
                -flood_fill(cur, blocked, size, limit=200),
            )
            if best is None or key < best_key:
                best = cur
                best_key = key
                break

        if d >= max_depth:
            continue

        for nxt in neighbors(cur, w, h):
            if nxt in parent:
                continue
            if nxt in blocked:
                continue
            # Do not route through immediate enemy-head danger for ordinary target paths.
            if nxt in enemy_maps["enemy_heads"] or nxt in enemy_maps["danger_1"]:
                continue
            parent[nxt] = cur
            depth[nxt] = d + 1
            q.append(nxt)

    if best is None:
        return None

    cur = best
    while parent[cur] is not None and parent[cur] != start:
        cur = parent[cur]
    return cur


# ==========================================================
# MOVE VALIDATION
# ==========================================================

def boost_path_cells(my_head, move, size):
    step1 = step_for_move(my_head, move, size)
    step2 = step_for_move(step1, move, size)
    return step1, step2


def is_move_clean(pos, hard_blocked, enemy_maps):
    if pos in hard_blocked:
        return False
    if pos in enemy_maps["enemy_heads"]:
        return False
    if pos in enemy_maps["danger_1"]:
        return False
    return True


def validates_boost_path(my_head, move, hard_blocked, enemy_maps, bad_apples, size, allow_bad=False):
    step1, step2 = boost_path_cells(my_head, move, size)

    for p in (step1, step2):
        if p in hard_blocked:
            return False
        if p in enemy_maps["enemy_heads"] or p in enemy_maps["danger_1"]:
            return False
        if p in bad_apples and not allow_bad:
            return False

    return True


# ==========================================================
# COMBAT HELPERS
# ==========================================================

def adjacent_sword_cut(my_head, candidate_moves, snakes, enemy_maps, hard_blocked, size):
    """
    Return a move that cuts a live enemy body segment immediately.
    We cannot know dead/alive from main_final.py because it does not pass alive,
    so we only attack body_no_head from listed snakes and never attack heads.
    """
    w, h = size
    best = None
    best_score = -10**9

    for move, pos in candidate_moves.items():
        if pos in hard_blocked:
            continue
        if pos in enemy_maps["enemy_heads"] or pos in enemy_maps["danger_1"]:
            continue

        for s in snakes:
            if s.get("head") == my_head:
                continue
            body = list(s.get("body", []))
            if pos in body[1:]:
                idx = body.index(pos)
                # Front/middle cuts matter more than tail cuts.
                cut_value = max(1, len(body) - idx)
                head_dist = wrap_dist(pos, s.get("head"), w, h)
                if head_dist <= 1:
                    continue
                score = 3000 + 180 * cut_value + 30 * head_dist
                if score > best_score:
                    best_score = score
                    best = move

    return best


def two_step_sword_setup(my_head, candidate_moves, snakes, enemy_maps, hard_blocked, size):
    """Move toward a body segment that can be cut next tick, but do not enter danger."""
    w, h = size
    enemy_body_targets = []
    for s in snakes:
        if s.get("head") == my_head:
            continue
        body = list(s.get("body", []))
        # Avoid tail-only obsession; use body[1:-1] first, tail if needed.
        enemy_body_targets.extend(body[1:-1] or body[1:])

    if not enemy_body_targets:
        return None

    best = None
    best_score = -10**9

    for move, pos in candidate_moves.items():
        if not is_move_clean(pos, hard_blocked, enemy_maps):
            continue

        nearest = min(wrap_dist(pos, b, w, h) for b in enemy_body_targets)
        if nearest > 1:
            continue

        score = 1200 - 250 * nearest + flood_fill(pos, hard_blocked, size, limit=250)
        score -= cell_risk_score(pos, enemy_maps)
        if score > best_score:
            best_score = score
            best = move

    return best


def should_activate_stack(my_body, clean_moves, hard_blocked, enemy_maps, size, inventory):
    if not has_stack(inventory):
        return False

    if not clean_moves:
        return True

    exposure = body_exposure_score(my_body, enemy_maps)
    if exposure >= 1200:
        return True

    # If all moves lead to tiny space, stack can save us from own-body trap.
    if clean_moves:
        best_space = max(flood_fill(pos, hard_blocked, size, limit=250) for pos in clean_moves.values())
        if best_space < 12 and len(my_body) >= 5:
            return True

    # If our body is inside immediate enemy predicted cells.
    if set(my_body) & enemy_maps["danger_1"]:
        return True

    return False


# ==========================================================
# MAIN DECISION FUNCTION
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, size, items, direction):
    global _tick, _last_boost, _last_sword, _last_stack, _prev_positions

    _tick += 1
    w, h = size

    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = list(my_snake.get("body", [])) if my_snake else [my_head]
    inventory = list(my_snake.get("inventory", [])) if my_snake else []

    # Main assumes body[0] is head. Own body except head is hard-blocked.
    own_body_no_head = set(my_body[1:])
    enemy_maps = build_enemy_maps(my_head, snakes, size)

    apples, bad_apples, swords, boosts, stars, speeds, stacks = classify_items(items)
    bad_set = set(bad_apples)

    # Obstacles from main include every visible body. Keep dead/corpse bodies hard-blocked.
    # Live enemy bodies are normally blocked, but a deliberate Sword/Star contact may override.
    all_obstacles = set(obstacles)
    hard_blocked = set(all_obstacles)
    hard_blocked.discard(my_head)

    # This remains hard for normal movement. Sword attacks are handled separately before scoring.
    normal_blocked = set(hard_blocked)

    # ======================================================
    # CANDIDATE MOVE GENERATION
    # ======================================================
    all_moves = {
        move: step_for_move(my_head, move, size)
        for move in legal_direction_names(direction)
    }

    # Moves that do not instantly die by body/dead-body/head/predicted-head collision.
    clean_moves = {
        move: pos for move, pos in all_moves.items()
        if is_move_clean(pos, normal_blocked, enemy_maps)
    }

    # Less strict emergency moves: avoid bodies and actual enemy heads, but may accept danger_1 if no choice.
    emergency_moves = {
        move: pos for move, pos in all_moves.items()
        if pos not in normal_blocked and pos not in enemy_maps["enemy_heads"]
    }

    # ======================================================
    # EMERGENCY STACK BEFORE BAD FALLBACK
    # ======================================================
    activate = None
    if should_activate_stack(my_body, clean_moves, normal_blocked, enemy_maps, size, inventory):
        if _tick - _last_stack > 2:
            activate = "STACK"
            _last_stack = _tick
            # With stack, our own body collapses; remove own body from blocked for choosing the escape direction.
            stack_blocked = set(normal_blocked) - own_body_no_head
            stack_moves = {
                move: pos for move, pos in all_moves.items()
                if pos not in stack_blocked
                and pos not in enemy_maps["enemy_heads"]
                and pos not in enemy_maps["danger_1"]
            }
            if stack_moves:
                clean_moves = stack_moves
                normal_blocked = stack_blocked

    # If still no clean moves, use emergency moves. Never simply return current direction if it kills us.
    if not clean_moves:
        if emergency_moves:
            best_emergency = max(
                emergency_moves,
                key=lambda m: (
                    flood_fill(emergency_moves[m], normal_blocked, size, limit=250),
                    -cell_risk_score(emergency_moves[m], enemy_maps),
                    escape_options(emergency_moves[m], normal_blocked, size),
                )
            )
            return best_emergency, activate
        # Last resort: choose any non-reverse move, but still prefer not into own body/dead body if possible.
        fallback = next(iter(all_moves.keys()), direction)
        return fallback, activate

    # ======================================================
    # IMMEDIATE SWORD CUT OVERRIDE
    # ======================================================
    sword_available = has_sword(inventory)
    star_available = has_star(inventory)

    if activate is None and sword_available:
        cut_move = adjacent_sword_cut(my_head, all_moves, snakes, enemy_maps, own_body_no_head, size)
        if cut_move is not None and _tick - _last_sword > 1:
            _last_sword = _tick
            return cut_move, "SWORD"

    # ======================================================
    # ADJACENT SAFE APPLE OVERRIDE
    # ======================================================
    # Take free adjacent apples unless there is an immediate sword cut or stack emergency.
    for move, pos in clean_moves.items():
        if pos in apples and pos not in enemy_maps["danger_2"]:
            return move, activate

    # ======================================================
    # TARGET PATH HINTS
    # ======================================================
    safe_apples = [
        a for a in apples
        if a not in normal_blocked
        and a not in enemy_maps["danger_1"]
        and not is_contested(a, my_head, snakes, size, margin=0)
    ]
    if not safe_apples:
        safe_apples = [a for a in apples if a not in normal_blocked and a not in enemy_maps["danger_1"]]

    safe_items = []
    for item_list, value in ((stacks, 5), (swords, 4), (boosts + speeds, 3), (stars, 2)):
        for t in item_list:
            if t in normal_blocked or t in enemy_maps["danger_1"]:
                continue
            if value == 2 and is_contested(t, my_head, snakes, size, margin=0):
                continue
            safe_items.append((t, value))

    apple_step = bfs_first_step(my_head, safe_apples, normal_blocked, enemy_maps, size, bad_apples, max_depth=60)
    item_step = bfs_first_step(my_head, [p for p, _ in safe_items], normal_blocked, enemy_maps, size, bad_apples, max_depth=50)

    apple_move = move_from_step(my_head, apple_step, size) if apple_step else None
    item_move = move_from_step(my_head, item_step, size) if item_step else None

    sword_setup_move = None
    if sword_available:
        sword_setup_move = two_step_sword_setup(my_head, clean_moves, snakes, enemy_maps, own_body_no_head, size)

    # ======================================================
    # SCORE ALL CLEAN MOVES
    # ======================================================
    best_move = None
    best_score = -10**18

    for move, pos in clean_moves.items():
        score = 0

        # 1. Survival and space.
        space = flood_fill(pos, normal_blocked, size, limit=650)
        esc = escape_options(pos, normal_blocked, size)
        score += space * 11
        score += esc * 75

        if space < 8:
            score -= 2500
        elif space < 18:
            score -= 900

        # 2. Enemy danger.
        risk = cell_risk_score(pos, enemy_maps)
        score -= risk

        # 3. Own future body exposure.
        future_body = [pos] + my_body[:-1]
        score -= body_exposure_score(future_body, enemy_maps) * 0.25

        # 4. Apple / bad apple.
        if pos in apples:
            score += 650
        if pos in bad_set:
            # Bad apples are allowed but expensive.
            score -= 700

        nd_apple = nearest_distance(pos, safe_apples or apples, size)
        if nd_apple is not None:
            score += 260 / (nd_apple + 1)

        # 5. Valuable items.
        if pos in stacks:
            score += 520
        if pos in swords:
            score += 480
        if pos in boosts or pos in speeds:
            score += 330
        if pos in stars and not is_contested(pos, my_head, snakes, size):
            score += 420

        # 6. Target-path nudges.
        if apple_move == move:
            score += 260
        if item_move == move:
            score += 180
        if sword_setup_move == move:
            score += 850

        # 7. Star logic: useful, not obsessive.
        if stars:
            safe_stars = [s for s in stars if not is_contested(s, my_head, snakes, size)]
            dstar = nearest_distance(pos, safe_stars, size)
            if dstar is not None and dstar <= 5:
                score += 170 / (dstar + 1)

        # 8. Boost activation safety preview.
        if has_boost(inventory):
            if validates_boost_path(my_head, move, normal_blocked, enemy_maps, bad_set, size, allow_bad=False):
                score += 60
            else:
                score -= 250

        # 9. Anti-loop and continuity.
        if move == direction:
            score += 35
        if pos in _prev_positions:
            score -= 60

        # 10. Keep distance from enemy heads unless attacking deliberately.
        for eh in enemy_maps["enemy_heads"]:
            d = wrap_dist(pos, eh, w, h)
            if d <= 1:
                score -= 5000
            elif d == 2:
                score -= 900
            elif d == 3:
                score -= 180

        if score > best_score:
            best_score = score
            best_move = move

    if best_move is None:
        # Safe fallback: best emergency move if any, otherwise current only if legal.
        if emergency_moves:
            best_move = max(
                emergency_moves,
                key=lambda m: flood_fill(emergency_moves[m], normal_blocked, size, limit=250)
            )
        elif direction in all_moves and all_moves[direction] not in normal_blocked:
            best_move = direction
        else:
            best_move = next(iter(all_moves.keys()), direction)

    final_pos = step_for_move(my_head, best_move, size)

    # ======================================================
    # ITEM ACTIVATION FINALIZATION
    # ======================================================
    # Stack is already allowed to override above.
    if activate is None and has_stack(inventory):
        # Panic stack if chosen cell is small/trappy or our body is exposed.
        if (_tick - _last_stack > 3 and
                (flood_fill(final_pos, normal_blocked, size, limit=200) < 10 or
                 body_exposure_score(my_body, enemy_maps) > 1600)):
            activate = "STACK"
            _last_stack = _tick

    if activate is None and sword_available:
        # Activate sword if next move is an intentional body cut.
        for s in snakes:
            if s.get("head") == my_head:
                continue
            body = list(s.get("body", []))
            if final_pos in body[1:] and final_pos not in enemy_maps["danger_1"]:
                if _tick - _last_sword > 1:
                    activate = "SWORD"
                    _last_sword = _tick
                break

    if activate is None and has_boost(inventory):
        # Use boost only when both cells are validated and it helps escape or race.
        if _tick - _last_boost > 4 and validates_boost_path(my_head, best_move, normal_blocked, enemy_maps, bad_set, size):
            danger_now = cell_risk_score(final_pos, enemy_maps) > 600
            item_race = final_pos in boosts or final_pos in speeds or final_pos in swords or final_pos in stacks
            open_escape = flood_fill(final_pos, normal_blocked, size, limit=300) > 45
            if danger_now or item_race or (open_escape and nearest_distance(final_pos, apples, size) is not None):
                activate = "BOOST"
                _last_boost = _tick

    if activate is None and has_star(inventory):
        # Star is not a kill button; use if it helps move through crowd safely or steal close items/apples.
        if stars or cell_risk_score(final_pos, enemy_maps) > 700:
            activate = "STAR"

    _prev_positions.append(my_head)

    # Final guard: never return a move that directly enters own body/dead body unless Stack is activating.
    guarded_pos = step_for_move(my_head, best_move, size)
    if guarded_pos in hard_blocked and activate != "STACK":
        alternatives = {
            m: p for m, p in clean_moves.items()
            if p not in hard_blocked and p not in enemy_maps["danger_1"]
        }
        if alternatives:
            best_move = max(
                alternatives,
                key=lambda m: flood_fill(alternatives[m], normal_blocked, size, limit=300)
            )
        elif has_stack(inventory):
            activate = "STACK"

    return best_move, activate
