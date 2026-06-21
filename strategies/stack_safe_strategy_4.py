from collections import deque
import heapq

# ==========================================================
# FINAL HYBRID COMBAT-CONTROL SURVIVAL STRATEGY
# ==========================================================
# Entry point preserved:
# choose_next_move(my_head, obstacles, snakes, size, items, direction)
# returns: (direction, activation_string_or_None)
#
# Philosophy:
# - Dead snake bodies are fixed hard obstacles.
# - Own body is a hard danger unless STACK is being used as emergency escape.
# - Live enemy bodies are normally avoided, but become attack targets when SWORD is available.
# - Stack protects against self-traps, sword threats, crowded contact, and body exposure.
# - Sword is used aggressively for safe cuts.
# - Star is useful but not blindly chased.
# - Bad apples are costly, not absolute walls.
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

# ---------------- Tunable weights ----------------
OPEN_SPACE_WEIGHT = 7.5
GOOD_APPLE_REWARD = 330
ADJACENT_APPLE_REWARD = 900
BAD_APPLE_PENALTY = 330
STAR_REWARD = 520
VALUABLE_ITEM_REWARD = 420
STACK_ITEM_REWARD = 520
SWORD_CUT_REWARD = 1500
SWORD_CUT_ADJACENT_REWARD = 5000
BOOST_ESCAPE_REWARD = 280
HEAD_DANGER_1_PENALTY = 1200
HEAD_DANGER_2_PENALTY = 520
HEAD_DANGER_3_PENALTY = 180
HEAD_RADIUS_1_PENALTY = 900
HEAD_RADIUS_2_PENALTY = 260
SWORD_THREAT_PENALTY = 950
SPEED_THREAT_PENALTY = 650
BOOSTED_CONTACT_PENALTY = 260
DEAD_END_PENALTY = 900
STRAIGHT_BONUS = 24
ANTI_LOOP_PENALTY = 45
STACK_COOLDOWN = 5
SWORD_COOLDOWN = 4
BOOST_COOLDOWN = 4

# ==========================================================
# BASIC HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(p, w, h):
    return (p[0] % w, p[1] % h)


def torus_dist(a, b, w, h):
    return min(abs(a[0] - b[0]), w - abs(a[0] - b[0])) + min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))


def neighbors(pos, w, h):
    return [wrap(add(pos, d), w, h) for d in DIRECTIONS.values()]


def move_from_step(head, step, w, h):
    for move, delta in DIRECTIONS.items():
        if wrap(add(head, delta), w, h) == step:
            return move
    return None


def step_for_move(head, move, size):
    w, h = size
    return wrap(add(head, DIRECTIONS[move]), w, h)


def has_keyword(values, *keywords):
    text = " ".join(str(v).lower() for v in (values or []))
    return any(k.lower() in text for k in keywords)


def snake_has_item_or_effect(snake, *keywords):
    inv = snake.get("inventory", []) or []
    effects = snake.get("active_effects", []) or []
    return has_keyword(inv, *keywords) or has_keyword(effects, *keywords)


def has_stack(snake):
    return snake_has_item_or_effect(snake, "stack")


def has_sword(snake):
    return snake_has_item_or_effect(snake, "sword")


def has_speed(snake):
    return snake_has_item_or_effect(snake, "speed", "boost")


def is_boosted(snake):
    return snake_has_item_or_effect(snake, "star", "shield")


def inventory_count(snake, *keywords):
    inv = snake.get("inventory", []) or []
    return sum(1 for item in inv if any(k.lower() in str(item).lower() for k in keywords))


def is_alive_snake(snake):
    # If main.py passes alive status, respect it. If unavailable, assume alive.
    return bool(snake.get("alive", True))


# ==========================================================
# ITEM CLASSIFICATION
# ==========================================================

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
# SPACE / PATHING
# ==========================================================

def flood_fill(start, blocked, size, limit=650):
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


def risk_aware_first_step(start, target, blocked, size, bad=set(), risk_map=None, allow_target_blocked=False):
    """Dijkstra on torus. Returns first step toward target.

    blocked cells are impossible unless target is allowed.
    bad cells are allowed with finite penalty.
    risk_map maps cell -> additional risk cost.
    """
    if start == target:
        return None
    w, h = size
    risk_map = risk_map or {}
    pq = [(0, 0, start)]
    came = {start: None}
    cost = {start: 0}
    counter = 0

    while pq:
        _, _, cur = heapq.heappop(pq)
        if cur == target:
            break

        for nxt in neighbors(cur, w, h):
            if nxt in blocked and not (allow_target_blocked and nxt == target):
                continue
            extra = 1
            if nxt in bad:
                extra += 7
            extra += risk_map.get(nxt, 0)
            new_cost = cost[cur] + extra
            if nxt not in cost or new_cost < cost[nxt]:
                cost[nxt] = new_cost
                came[nxt] = cur
                counter += 1
                priority = new_cost + torus_dist(nxt, target, w, h)
                heapq.heappush(pq, (priority, counter, nxt))

    if target not in came:
        return None

    cur = target
    while came[cur] is not None and came[cur] != start:
        cur = came[cur]
    return cur


# ==========================================================
# ENEMY PREDICTION
# ==========================================================

def reachable_cells_from(head, body, size, depth=3, speed_active=False):
    w, h = size
    body_set = set(body)
    zones_by_depth = {i: set() for i in range(1, depth + 1)}
    frontier = {head}

    for step in range(1, depth + 1):
        next_frontier = set()
        for pos in frontier:
            candidates = neighbors(pos, w, h)
            if speed_active:
                expanded = set(candidates)
                for c in candidates:
                    expanded.update(neighbors(c, w, h))
                candidates = list(expanded)
            for nxt in candidates:
                if nxt in body_set and nxt != head:
                    continue
                zones_by_depth[step].add(nxt)
                next_frontier.add(nxt)
        frontier = next_frontier or frontier
    return zones_by_depth


def local_radius(center, radius, size):
    w, h = size
    cells = set()
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if abs(dx) + abs(dy) <= radius:
                cells.add(wrap((center[0] + dx, center[1] + dy), w, h))
    return cells


def build_board_sets(my_head, snakes, size):
    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = set(my_snake.get("body", [])) if my_snake else {my_head}
    my_body_no_head = {p for p in my_body if p != my_head}

    live_enemies = []
    dead_body_blockers = set()
    live_enemy_bodies = set()
    live_enemy_heads = set()

    for s in snakes:
        body = list(s.get("body", []))
        if not body or s.get("head") == my_head:
            continue
        if is_alive_snake(s):
            live_enemies.append(s)
            live_enemy_bodies.update(body)
            live_enemy_heads.add(s.get("head", body[0]))
        else:
            dead_body_blockers.update(body)

    return my_snake, my_body, my_body_no_head, live_enemies, dead_body_blockers, live_enemy_bodies, live_enemy_heads


def build_enemy_maps(live_enemies, size):
    danger_1, danger_2, danger_3 = set(), set(), set()
    head_radius_1, head_radius_2 = set(), set()
    sword_threat, speed_threat, boosted_threat = set(), set(), set()

    for s in live_enemies:
        body = list(s.get("body", []))
        if not body:
            continue
        head = s.get("head", body[0])
        speed_active = has_speed(s)
        zones = reachable_cells_from(head, body, size, depth=3, speed_active=speed_active)
        danger_1.update(zones[1])
        danger_2.update(zones[2])
        danger_3.update(zones[3])
        head_radius_1.update(local_radius(head, 1, size))
        head_radius_2.update(local_radius(head, 2, size))
        if has_sword(s):
            sword_threat.update(zones[1] | zones[2])
            for z in list(zones[1] | zones[2]):
                sword_threat.update(local_radius(z, 1, size))
        if speed_active:
            speed_threat.update(zones[1] | zones[2])
        if is_boosted(s):
            boosted_threat.update(zones[1] | zones[2] | zones[3])

    risk_map = {}
    for p in danger_3:
        risk_map[p] = max(risk_map.get(p, 0), 5)
    for p in danger_2:
        risk_map[p] = max(risk_map.get(p, 0), 15)
    for p in danger_1:
        risk_map[p] = max(risk_map.get(p, 0), 40)
    for p in head_radius_2:
        risk_map[p] = max(risk_map.get(p, 0), 12)
    for p in head_radius_1:
        risk_map[p] = max(risk_map.get(p, 0), 30)
    for p in sword_threat:
        risk_map[p] = max(risk_map.get(p, 0), 28)
    for p in boosted_threat:
        risk_map[p] = max(risk_map.get(p, 0), 12)

    return {
        "danger_1": danger_1,
        "danger_2": danger_2,
        "danger_3": danger_3,
        "head_radius_1": head_radius_1,
        "head_radius_2": head_radius_2,
        "sword_threat": sword_threat,
        "speed_threat": speed_threat,
        "boosted_threat": boosted_threat,
        "risk_map": risk_map,
    }


# ==========================================================
# MOVE SAFETY / SIMULATION
# ==========================================================

def path_cells_for_move(head, move, size, speed=False):
    first = step_for_move(head, move, size)
    if not speed:
        return [first]
    second = step_for_move(first, move, size)
    return [first, second]


def is_move_clean(move, my_head, size, hard_blocked, enemy_maps, speed=False):
    cells = path_cells_for_move(my_head, move, size, speed=speed)
    for c in cells:
        if c in hard_blocked:
            return False
        if c in enemy_maps["danger_1"]:
            return False
    return True


def move_risk_score(pos, enemy_maps):
    score = 0
    if pos in enemy_maps["danger_1"]:
        score -= HEAD_DANGER_1_PENALTY
    if pos in enemy_maps["danger_2"]:
        score -= HEAD_DANGER_2_PENALTY
    if pos in enemy_maps["danger_3"]:
        score -= HEAD_DANGER_3_PENALTY
    if pos in enemy_maps["head_radius_1"]:
        score -= HEAD_RADIUS_1_PENALTY
    if pos in enemy_maps["head_radius_2"]:
        score -= HEAD_RADIUS_2_PENALTY
    if pos in enemy_maps["sword_threat"]:
        score -= SWORD_THREAT_PENALTY
    if pos in enemy_maps["speed_threat"]:
        score -= SPEED_THREAT_PENALTY
    if pos in enemy_maps["boosted_threat"]:
        score -= BOOSTED_CONTACT_PENALTY
    return score


# ==========================================================
# STACK / SWORD LOGIC
# ==========================================================

def body_exposure_score(my_body, enemy_maps):
    exposure = 0
    for seg in my_body:
        if seg in enemy_maps["sword_threat"]:
            exposure += 5
        elif seg in enemy_maps["danger_1"]:
            exposure += 4
        elif seg in enemy_maps["danger_2"]:
            exposure += 2
        elif seg in enemy_maps["head_radius_1"]:
            exposure += 2
    return exposure


def find_sword_cut(my_head, live_enemies, hard_blocked_except_enemy, enemy_maps, size, bad):
    """Return (move, target, dist_score) for a safe sword cut if possible.

    Live enemy bodies are targets, not hard blocked. Dead bodies and own body remain blocked.
    Prefer non-tail body segments and avoid heads.
    """
    w, h = size
    candidates = []

    for s in live_enemies:
        body = list(s.get("body", []))
        if len(body) < 2:
            continue
        head = s.get("head", body[0])
        # skip head, prefer middle/front body, not just tail
        for idx, seg in enumerate(body[1:], start=1):
            d = torus_dist(my_head, seg, w, h)
            if d > 3:
                continue
            # Earlier body index is closer to head in this codebase if body[0] is head.
            segment_value = max(1, len(body) - idx)
            candidates.append((d, -segment_value, seg, head, s))

    candidates.sort()

    for d, _, target, enemy_head, _enemy in candidates:
        # Adjacent cut: move straight into body segment if this does not enter head danger.
        if d == 1:
            mv = move_from_step(my_head, target, w, h)
            if mv and target not in hard_blocked_except_enemy and target not in enemy_maps["danger_1"]:
                return mv, target, d

        # 2-3 step cut path: path toward target but do not pass through dead/own/head cells.
        blocked = set(hard_blocked_except_enemy)
        # target is allowed even though it is an enemy body cell
        step = risk_aware_first_step(
            my_head,
            target,
            blocked,
            size,
            bad=bad,
            risk_map=enemy_maps["risk_map"],
            allow_target_blocked=True,
        )
        if not step:
            continue
        mv = move_from_step(my_head, step, w, h)
        if not mv:
            continue
        if step in hard_blocked_except_enemy or step in enemy_maps["danger_1"] or step in enemy_maps["head_radius_1"]:
            continue
        return mv, target, d

    return None, None, None


def should_activate_stack(my_snake, my_body, my_head, size, moves, hard_blocked_normal, enemy_maps, live_enemies, bad):
    if not my_snake or not has_stack(my_snake):
        return False

    # Cooldown to avoid spamming if the server keeps item in inventory for one tick.
    if hasattr(choose_next_move, "last_stack_tick"):
        if choose_next_move.tick - choose_next_move.last_stack_tick < STACK_COOLDOWN:
            return False

    exposure = body_exposure_score(my_body, enemy_maps)
    if exposure >= 6:
        return True

    # If every normal move is bad/blocked/head-danger, stack for emergency compression.
    clean_count = 0
    for mv, pos in moves.items():
        if pos not in hard_blocked_normal and pos not in enemy_maps["danger_1"] and pos not in bad:
            clean_count += 1
    if clean_count == 0:
        return True

    # Long snake + enemy close to body = stack proactively.
    if len(my_body) >= 8 and exposure >= 3:
        return True

    # Sword or speed enemy can contact our body soon.
    for s in live_enemies:
        if not (has_sword(s) or has_speed(s)):
            continue
        zones = reachable_cells_from(s.get("head"), s.get("body", []), size, depth=2, speed_active=has_speed(s))
        attack_zone = zones[1] | zones[2]
        if has_sword(s):
            expanded = set(attack_zone)
            for z in list(attack_zone):
                expanded.update(local_radius(z, 1, size))
            attack_zone = expanded
        if set(my_body) & attack_zone:
            return True

    return False


# ==========================================================
# TARGET SELECTION
# ==========================================================

def nearest_step_toward_targets(my_head, targets, blocked, size, bad, enemy_maps, target_bonus=None):
    if not targets:
        return None, None
    w, h = size
    target_bonus = target_bonus or (lambda t: 0)
    best = None
    best_score = -10**18
    for t in targets:
        step = risk_aware_first_step(my_head, t, blocked, size, bad=bad, risk_map=enemy_maps["risk_map"])
        if not step:
            continue
        move = move_from_step(my_head, step, w, h)
        if not move:
            continue
        d = torus_dist(my_head, t, w, h)
        score = target_bonus(t) - d * 30 - enemy_maps["risk_map"].get(step, 0) * 8
        if step in bad:
            score -= BAD_APPLE_PENALTY
        if score > best_score:
            best_score = score
            best = (move, t)
    return best if best else (None, None)


def star_is_good(my_head, star, live_enemies, size, enemy_maps):
    w, h = size
    my_d = torus_dist(my_head, star, w, h)
    enemy_d = min((torus_dist(s.get("head"), star, w, h) for s in live_enemies), default=999)
    # Need to be clearly closer; equality is contested.
    if my_d >= enemy_d:
        return False
    # Do not chase far star over useful apples/items.
    if my_d > 8 and enemy_d - my_d < 3:
        return False
    return True


# ==========================================================
# MAIN STRATEGY
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction):
    if not hasattr(choose_next_move, "tick"):
        choose_next_move.tick = 0
        choose_next_move.prev_positions = deque(maxlen=8)
        choose_next_move.last_stack_tick = -100
        choose_next_move.last_sword_tick = -100
        choose_next_move.last_boost_tick = -100
    choose_next_move.tick += 1

    w, h = field_size
    size = field_size

    my_snake, my_body, my_body_no_head, live_enemies, dead_body_blockers, live_enemy_bodies, live_enemy_heads = build_board_sets(my_head, snakes, size)
    if my_snake is None:
        # Safe fallback; should rarely happen.
        return current_direction, None

    apples, bad_list, swords, boosts, stars, speeds, stacks = classify_items(items)
    bad = set(bad_list)
    enemy_maps = build_enemy_maps(live_enemies, size)

    my_has_stack = has_stack(my_snake)
    my_has_sword = has_sword(my_snake)
    my_has_speed = has_speed(my_snake)
    my_boosted = is_boosted(my_snake)

    moves = {mv: step_for_move(my_head, mv, size) for mv in DIRECTIONS}
    forbidden = OPPOSITE.get(current_direction)

    # Dead bodies and own body are truly hard. Live enemy bodies are hard for normal movement,
    # but not for sword-cut planning.
    hard_blocked_base = set(my_body_no_head) | set(dead_body_blockers)
    hard_blocked_normal = hard_blocked_base | set(live_enemy_bodies) | set(live_enemy_heads)
    hard_blocked_attack = hard_blocked_base | set(live_enemy_heads) | set(dead_body_blockers)

    # If stack is available and needed, we may allow own-body compression in the final emergency evaluation.
    stack_needed = should_activate_stack(
        my_snake, my_body, my_head, size, moves, hard_blocked_normal, enemy_maps, live_enemies, bad
    )

    # ---------------- SWORD: immediate / near cut ----------------
    sword_move, sword_target, sword_distance = (None, None, None)
    if my_has_sword:
        sword_move, sword_target, sword_distance = find_sword_cut(
            my_head, live_enemies, hard_blocked_attack, enemy_maps, size, bad
        )
        # Immediate safe sword cut beats most things except critical stack emergency.
        if sword_move and sword_distance == 1:
            sword_step = moves[sword_move]
            critical_stack = stack_needed and (body_exposure_score(my_body, enemy_maps) >= 8 or sword_step in enemy_maps["danger_1"])
            if not critical_stack:
                choose_next_move.last_sword_tick = choose_next_move.tick
                choose_next_move.prev_positions.append(my_head)
                return sword_move, "SWORD"

    # ---------------- Build legal candidates ----------------
    candidates = []
    for mv, pos in moves.items():
        if mv == forbidden:
            continue
        cells = path_cells_for_move(my_head, mv, size, speed=my_has_speed)
        # Normal mode: cannot pass through own/dead/live body/head.
        blocked_hit = any(c in hard_blocked_normal for c in cells)
        # Stack emergency can save own-body/trap exposure, but not dead bodies.
        dead_hit = any(c in dead_body_blockers for c in cells)
        own_hit = any(c in my_body_no_head for c in cells)
        live_hit = any(c in live_enemy_bodies or c in live_enemy_heads for c in cells)

        if blocked_hit and not (stack_needed and my_has_stack and own_hit and not dead_hit and not live_hit):
            continue
        # Never choose dead-body collision.
        if dead_hit:
            continue
        # Never choose live enemy contact unless sword move is specifically chosen elsewhere.
        if live_hit:
            continue
        candidates.append((mv, pos, cells))

    # If no normal candidates but stack can compress our own body, try any move that avoids dead/live enemy.
    if not candidates and my_has_stack:
        for mv, pos in moves.items():
            if mv == forbidden:
                continue
            cells = path_cells_for_move(my_head, mv, size, speed=False)
            if any(c in dead_body_blockers or c in live_enemy_bodies or c in live_enemy_heads for c in cells):
                continue
            candidates.append((mv, pos, cells))
        if candidates:
            stack_needed = True

    if not candidates:
        # Last-resort: choose a non-opposite move with lowest immediate body danger, never dead-body if possible.
        best_mv = current_direction
        best_score = -10**18
        for mv, pos in moves.items():
            if mv == forbidden:
                continue
            score = 0
            if pos in dead_body_blockers:
                score -= 100000
            if pos in my_body_no_head:
                score -= 50000
            if pos in live_enemy_heads:
                score -= 60000
            if pos in live_enemy_bodies:
                score -= 40000
            score += flood_fill(pos, hard_blocked_base | dead_body_blockers, size) * OPEN_SPACE_WEIGHT
            if score > best_score:
                best_score = score
                best_mv = mv
        activation = "STACK" if my_has_stack else None
        if activation == "STACK":
            choose_next_move.last_stack_tick = choose_next_move.tick
        choose_next_move.prev_positions.append(my_head)
        return best_mv, activation

    # ---------------- Adjacent apple: high priority unless sword cut or emergency stack ----------------
    adjacent_good = []
    for mv, pos, _cells in candidates:
        if pos in apples and pos not in enemy_maps["danger_1"] and pos not in enemy_maps["head_radius_1"]:
            adjacent_good.append(mv)

    # ---------------- Target path suggestions ----------------
    # Normal path blockers: dead + own + live bodies/heads.
    path_blocked_normal = set(hard_blocked_normal)

    # Valuable item targets. Stack gets extra value if enemies are pressuring us.
    valuable_targets = []
    valuable_targets += [(p, "STACK") for p in stacks]
    valuable_targets += [(p, "SWORD") for p in swords]
    valuable_targets += [(p, "BOOST") for p in boosts + speeds]

    safe_stars = [s for s in stars if star_is_good(my_head, s, live_enemies, size, enemy_maps)]

    # ---------------- Score all candidate moves ----------------
    best_move = None
    best_score = -10**18
    best_reason = None

    for mv, pos, cells in candidates:
        score = 0
        last_cell = cells[-1]

        # Survival/open space. Flood fill blocks all bodies, dead bodies included.
        space_blocked = set(path_blocked_normal)
        space = flood_fill(last_cell, space_blocked, size)
        score += space * OPEN_SPACE_WEIGHT
        if space < max(10, len(my_body) * 2):
            score -= DEAD_END_PENALTY

        exits = escape_options(last_cell, space_blocked, size)
        score += exits * 55
        if exits <= 1:
            score -= 480

        # Enemy danger.
        for c in cells:
            score += move_risk_score(c, enemy_maps)

        # Bad apples are costly but allowed if they create better future.
        for c in cells:
            if c in bad:
                score -= BAD_APPLE_PENALTY

        # Good apples.
        for c in cells:
            if c in apples:
                score += ADJACENT_APPLE_REWARD
        if apples:
            nearest_apple = min(apples, key=lambda a: torus_dist(last_cell, a, w, h))
            d = torus_dist(last_cell, nearest_apple, w, h)
            # Do not overvalue contested apples.
            enemy_to_apple = min((torus_dist(s.get("head"), nearest_apple, w, h) for s in live_enemies), default=999)
            contest_penalty = 160 if enemy_to_apple <= d else 0
            score += GOOD_APPLE_REWARD / (d + 1) - contest_penalty

        # Valuable items.
        for p in stacks:
            d = torus_dist(last_cell, p, w, h)
            score += (STACK_ITEM_REWARD if stack_needed else VALUABLE_ITEM_REWARD) / (d + 1)
        for p in swords:
            d = torus_dist(last_cell, p, w, h)
            score += VALUABLE_ITEM_REWARD / (d + 1)
        for p in boosts + speeds:
            d = torus_dist(last_cell, p, w, h)
            score += (VALUABLE_ITEM_REWARD + BOOST_ESCAPE_REWARD) / (d + 1)

        # Star: medium-high only when we are favoured.
        for st in safe_stars:
            d0 = torus_dist(my_head, st, w, h)
            d1 = torus_dist(last_cell, st, w, h)
            if d1 < d0:
                score += STAR_REWARD / (d1 + 1) + 80

        # Sword cut targeting.
        if my_has_sword and sword_target:
            d0 = torus_dist(my_head, sword_target, w, h)
            d1 = torus_dist(last_cell, sword_target, w, h)
            if d1 < d0:
                score += SWORD_CUT_REWARD / (d1 + 1) + 350
            if mv == sword_move:
                score += 850

        # Boosted star contact: only opportunistic, not chase across map.
        if my_boosted:
            for s in live_enemies:
                for b in s.get("body", [])[:3]:
                    if torus_dist(last_cell, b, w, h) <= 1:
                        score += 120

        # Enemy distance buffer, especially heads.
        for s in live_enemies:
            eh = s.get("head")
            d = torus_dist(last_cell, eh, w, h)
            if d == 0:
                score -= 100000
            elif d == 1:
                score -= 900
            elif d == 2:
                score -= 240
            else:
                score += min(d, 8) * 4

        # Stability / anti-loop.
        if mv == current_direction:
            score += STRAIGHT_BONUS
        if hasattr(choose_next_move, "prev_positions") and last_cell in choose_next_move.prev_positions:
            score -= ANTI_LOOP_PENALTY

        # If stack is needed, favor moves that keep us open after stack.
        if stack_needed and my_has_stack:
            score += 500
            if own_hit if False else False:
                pass

        if score > best_score:
            best_score = score
            best_move = mv
            best_reason = "score"

    activation = None

    # ---------------- Activation priority ----------------
    # Stack overrides if actual survival/body-exposure emergency.
    if stack_needed and my_has_stack:
        activation = "STACK"
        choose_next_move.last_stack_tick = choose_next_move.tick
    # Sword for near cut if not stack-critical.
    elif my_has_sword and sword_move and sword_distance is not None and sword_distance <= 2:
        if choose_next_move.tick - choose_next_move.last_sword_tick >= SWORD_COOLDOWN:
            best_move = sword_move
            activation = "SWORD"
            choose_next_move.last_sword_tick = choose_next_move.tick
    # Boost/speed if it helps escape or reach a clear valuable target, but not every time.
    elif has_speed(my_snake) and choose_next_move.tick - choose_next_move.last_boost_tick >= BOOST_COOLDOWN:
        nearest_enemy_dist = min((torus_dist(my_head, s.get("head"), w, h) for s in live_enemies), default=999)
        if nearest_enemy_dist <= 4 and is_move_clean(best_move, my_head, size, hard_blocked_normal, enemy_maps, speed=True):
            activation = "BOOST"
            choose_next_move.last_boost_tick = choose_next_move.tick

    # Adjacent safe apple can override star/item wandering if no combat/stack action.
    if activation is None and adjacent_good and not (my_has_sword and sword_distance == 1):
        # choose adjacent apple with best safety/open space
        best_adj = None
        best_adj_score = -10**18
        for mv in adjacent_good:
            pos = moves[mv]
            s = flood_fill(pos, path_blocked_normal, size) * OPEN_SPACE_WEIGHT + move_risk_score(pos, enemy_maps)
            if s > best_adj_score:
                best_adj_score = s
                best_adj = mv
        if best_adj:
            best_move = best_adj

    # Explicit safe star path if no immediate apple/sword and star is favourable.
    if activation is None and safe_stars and not adjacent_good and not (my_has_sword and sword_distance and sword_distance <= 2):
        best_star = min(safe_stars, key=lambda st: torus_dist(my_head, st, w, h))
        step = risk_aware_first_step(my_head, best_star, path_blocked_normal, size, bad=bad, risk_map=enemy_maps["risk_map"])
        mv = move_from_step(my_head, step, w, h) if step else None
        if mv and any(mv == c[0] for c in candidates):
            best_move = mv

    # Validate final move one more time. Never crash into own/dead/live body as normal movement.
    final_cells = path_cells_for_move(my_head, best_move, size, speed=False) if best_move else []
    if not best_move or any(c in dead_body_blockers or c in live_enemy_heads for c in final_cells):
        # choose safest candidate by open space only
        best_move = max(candidates, key=lambda x: flood_fill(x[1], path_blocked_normal, size) + escape_options(x[1], path_blocked_normal, size))[0]
    if final_cells and any(c in my_body_no_head for c in final_cells) and my_has_stack:
        activation = "STACK"
        choose_next_move.last_stack_tick = choose_next_move.tick

    choose_next_move.prev_positions.append(my_head)
    return best_move, activation
