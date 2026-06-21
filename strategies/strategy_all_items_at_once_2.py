from collections import deque
import heapq

# ==========================================================
# FINAL HYBRID COMBAT-CONTROL SURVIVAL STRATEGY
# Compatible with main2.py choose_next_move(...) entry point.
# Returns: (direction, activate) where activate may be None/SWORD/BOOST/STACK/STAR
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

# Tunable weights
BLOCKED_PENALTY = 10**9
SELF_COLLISION_PENALTY = 10**8
DEAD_BODY_PENALTY = 10**8
ENEMY_HEAD_1_PENALTY = 50000
ENEMY_HEAD_2_PENALTY = 9000
ENEMY_HEAD_3_PENALTY = 2500
BAD_APPLE_PENALTY = 900
BAD_APPLE_NEAR_PENALTY = 120
LOW_SPACE_PENALTY = 3500
SWORD_CUT_REWARD = 60000
SWORD_PATH_REWARD = 9000
STACK_ESCAPE_REWARD = 100000
STAR_REWARD = 2200
ITEM_REWARD = 1400
APPLE_REWARD = 2600
CENTER_APPLE_BONUS = 700
OPEN_SPACE_WEIGHT = 13
STRAIGHT_BONUS = 20

# Simple cooldown memory so we do not spam activations every tick if server ignores it.
_tick = 0
_last_sword = -100
_last_boost = -100
_last_stack = -100
_last_star = -100

SWORD_COOLDOWN = 3
BOOST_COOLDOWN = 5
STACK_COOLDOWN = 3
STAR_COOLDOWN = 6


# ==========================================================
# BASIC HELPERS
# ==========================================================

def add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def wrap(p, w, h):
    return (p[0] % w, p[1] % h)


def wrap_dist(a, b, w, h):
    dx = min(abs(a[0] - b[0]), w - abs(a[0] - b[0]))
    dy = min(abs(a[1] - b[1]), h - abs(a[1] - b[1]))
    return dx + dy


def neighbors(pos, w, h):
    for d in DIRECTIONS.values():
        yield wrap(add(pos, d), w, h)


def move_from_step(step, head, w, h):
    dx = (step[0] - head[0]) % w
    dy = (step[1] - head[1]) % h
    if dx == 1 and dy == 0:
        return "EAST"
    if dx == w - 1 and dy == 0:
        return "WEST"
    if dy == 1 and dx == 0:
        return "SOUTH"
    if dy == h - 1 and dx == 0:
        return "NORTH"
    return None


def norm_pos(p):
    try:
        return (int(p[0]), int(p[1]))
    except Exception:
        return None


def item_positions(items, keyword):
    out = []
    for it in items:
        kind = str(getattr(it, "kind", "")).lower()
        pos = norm_pos(getattr(it, "position", None))
        if pos is not None and keyword in kind:
            out.append(pos)
    return out


# ==========================================================
# ITEMS / EFFECTS
# ==========================================================

def classify_items(items):
    apples, bad, stars, swords, boosts, stacks = [], [], [], [], [], []
    for it in items:
        kind = str(getattr(it, "kind", "")).lower()
        pos = norm_pos(getattr(it, "position", None))
        if pos is None:
            continue
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


def has_token(snake, *names):
    inv = snake.get("inventory", []) if snake else []
    joined_names = tuple(n.lower() for n in names)
    return any(any(n in str(item).lower() for n in joined_names) for item in inv)


def has_effect(snake, *names):
    if not snake:
        return False
    effects = snake.get("active_effects", []) or []
    joined_names = tuple(n.lower() for n in names)
    for e in effects:
        if isinstance(e, dict):
            txt = str(e.get("effect", "")).lower()
            ticks = int(e.get("remaining_ticks", 1) or 0)
        else:
            txt = str(getattr(e, "effect", e)).lower()
            ticks = int(getattr(e, "remaining_ticks", 1) or 0)
        if ticks != 0 and any(n in txt for n in joined_names):
            return True
    return False


# ==========================================================
# FLOOD / ESCAPE SAFETY
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


def emergency_escape_score(pos, blocked, size):
    esc = escape_options(pos, blocked, size)
    if esc <= 0:
        return -16000
    if esc == 1:
        return -7000
    if esc == 2:
        return -1200
    return esc * 80


# ==========================================================
# ENEMY PREDICTION
# ==========================================================

def enemy_prediction(snakes, my_head, size):
    """Predict enemy head cells 1, 2, and 3 steps ahead on torus grid.
    Also returns radius zones around current enemy heads and sword threat zones.
    """
    w, h = size
    d1, d2, d3 = set(), set(), set()
    r1, r2 = set(), set()
    sword_threat = set()
    boosted_threat = set()
    enemy_heads = set()

    for s in snakes:
        head = s.get("head")
        if not head or head == my_head:
            continue
        enemy_heads.add(head)
        body = set(s.get("body", []))
        body_no_head = set(s.get("body", [])[1:])
        speed = has_token(s, "boost", "speed") or has_effect(s, "boost", "speed")
        sword = has_token(s, "sword") or has_effect(s, "sword")
        boosted = has_token(s, "star", "shield") or has_effect(s, "star", "shield", "boost")

        # Current head radius zones.
        for x in range(w):
            pass
        for dx, dy in DIRECTIONS.values():
            p1 = wrap((head[0] + dx, head[1] + dy), w, h)
            r1.add(p1)
            for dx2, dy2 in DIRECTIONS.values():
                r2.add(wrap((p1[0] + dx2, p1[1] + dy2), w, h))

        first = []
        for n in neighbors(head, w, h):
            # Enemy cannot usually reverse into its own neck, and usually avoids body;
            # but if no moves exist we relax it below.
            if n in body_no_head:
                continue
            first.append(n)
        if not first:
            first = list(neighbors(head, w, h))

        step1_cells = set(first)
        if speed:
            # speed enemies can pass through a second cell in same tick; mark both.
            extra = set()
            for p in step1_cells:
                for n in neighbors(p, w, h):
                    if n not in body_no_head:
                        extra.add(n)
            step1_cells |= extra

        d1 |= step1_cells

        step2_cells = set()
        for p in step1_cells:
            for n in neighbors(p, w, h):
                if n not in body_no_head:
                    step2_cells.add(n)
        d2 |= step2_cells

        step3_cells = set()
        for p in step2_cells:
            for n in neighbors(p, w, h):
                if n not in body_no_head:
                    step3_cells.add(n)
        d3 |= step3_cells

        if sword:
            # Sword attack zone: where enemy could reach plus adjacent slash/contact cells.
            sword_threat |= step1_cells | step2_cells
            for p in list(step1_cells | step2_cells):
                sword_threat.update(neighbors(p, w, h))

        if boosted:
            boosted_threat |= step1_cells | step2_cells

    return {
        "d1": d1,
        "d2": d2,
        "d3": d3,
        "r1": r1,
        "r2": r2,
        "sword": sword_threat,
        "boosted": boosted_threat,
        "heads": enemy_heads,
    }


# ==========================================================
# PATHFINDING WITH RISK COST
# ==========================================================

def risk_cost(pos, bad_apples, zones):
    c = 1
    if pos in bad_apples:
        c += 18
    if pos in zones["d1"] or pos in zones["r1"]:
        c += 1000
    elif pos in zones["d2"] or pos in zones["r2"]:
        c += 120
    elif pos in zones["d3"]:
        c += 35
    if pos in zones["sword"]:
        c += 250
    if pos in zones["boosted"]:
        c += 120
    return c


def astar_next(start, goal, blocked, size, bad_apples, zones, allow_bad=True):
    if start == goal:
        return start
    w, h = size
    pq = [(wrap_dist(start, goal, w, h), 0, start)]
    came = {}
    cost = {start: 0}

    while pq:
        _, g, cur = heapq.heappop(pq)
        if cur == goal:
            break
        for nxt in neighbors(cur, w, h):
            if nxt in blocked:
                continue
            if not allow_bad and nxt in bad_apples:
                continue
            ng = g + risk_cost(nxt, bad_apples, zones)
            if nxt not in cost or ng < cost[nxt]:
                cost[nxt] = ng
                came[nxt] = cur
                heapq.heappush(pq, (ng + wrap_dist(nxt, goal, w, h), ng, nxt))

    if goal not in came:
        return None
    cur = goal
    while came[cur] != start:
        cur = came[cur]
    return cur


# ==========================================================
# TARGET CONTEST / ITEMS
# ==========================================================

def is_contested(pos, my_head, snakes, size, strict_equal=True):
    w, h = size
    my_d = wrap_dist(my_head, pos, w, h)
    for s in snakes:
        hpos = s.get("head")
        if not hpos or hpos == my_head:
            continue
        ed = wrap_dist(hpos, pos, w, h)
        if ed < my_d or (strict_equal and ed == my_d):
            return True
    return False


def nearest_distance(pos, targets, size):
    if not targets:
        return 9999
    w, h = size
    return min(wrap_dist(pos, t, w, h) for t in targets)


def center_region(size):
    w, h = size
    c = (w // 2, h // 2)
    r = max(3, min(w, h) // 5)
    return c, r


# ==========================================================
# COMBAT / STACK ANALYSIS
# ==========================================================

def find_sword_cut_moves(my_head, snakes, blocked_static, zones, size):
    """Return direct 1-step cut moves and best 2-step approach targets.
    Enemy heads are not targeted; body segments after head are preferred.
    """
    w, h = size
    direct = {}
    approach = {}

    for move, delta in DIRECTIONS.items():
        nxt = wrap(add(my_head, delta), w, h)
        if nxt in zones["d1"] or nxt in zones["r1"]:
            continue
        for s in snakes:
            if s.get("head") == my_head:
                continue
            body = list(s.get("body", []))
            # body[0] is head in this project; cut body segments only.
            for idx, seg in enumerate(body[1:], start=1):
                if seg == nxt:
                    # Middle/front body cut is more valuable than tail.
                    direct[move] = max(direct.get(move, 0), SWORD_CUT_REWARD + max(0, len(body) - idx) * 800)

    # 2-step approach: move toward an adjacent-to-enemy-body cell.
    enemy_body_targets = []
    for s in snakes:
        if s.get("head") == my_head:
            continue
        body = list(s.get("body", []))
        for idx, seg in enumerate(body[1:], start=1):
            val = max(0, len(body) - idx) * 200
            enemy_body_targets.append((seg, SWORD_PATH_REWARD + val))

    for move, delta in DIRECTIONS.items():
        nxt = wrap(add(my_head, delta), w, h)
        if nxt in blocked_static or nxt in zones["d1"] or nxt in zones["r1"]:
            continue
        if enemy_body_targets:
            best = 0
            for target, val in enemy_body_targets:
                d = wrap_dist(nxt, target, w, h)
                if d <= 2:
                    best = max(best, val - d * 1500)
            if best > 0:
                approach[move] = best

    return direct, approach


def body_exposure(my_body, zones):
    body = set(my_body)
    score = 0
    score += len(body & zones["sword"]) * 12
    score += len(body & zones["d1"]) * 6
    score += len(body & zones["d2"]) * 3
    return score


def should_stack(my_body, chosen_pos, blocked_without_self, zones, size, has_stack, legal_clean_moves):
    if not has_stack:
        return False
    body = set(my_body)
    if chosen_pos in body:
        return True
    if not legal_clean_moves:
        return True
    if chosen_pos in blocked_without_self:
        return True
    if escape_options(chosen_pos, blocked_without_self | body, size) <= 1:
        return True
    if body_exposure(my_body, zones) >= 10:
        return True
    return False


def speed_path_cells(my_head, move, size):
    w, h = size
    d = DIRECTIONS[move]
    first = wrap(add(my_head, d), w, h)
    second = wrap(add(first, d), w, h)
    return [first, second]


# ==========================================================
# MAIN STRATEGY
# ==========================================================

def choose_next_move(my_head, obstacles, snakes, field_size, items, current_direction):
    global _tick, _last_sword, _last_boost, _last_stack, _last_star
    _tick += 1

    w, h = field_size
    my_snake = next((s for s in snakes if s.get("head") == my_head), None)
    my_body = list(my_snake.get("body", [])) if my_snake else [my_head]
    my_body_set = set(my_body)
    my_body_no_head = set(my_body[1:]) if len(my_body) > 1 else set()
    inventory = my_snake.get("inventory", []) if my_snake else []

    has_sword = has_token(my_snake, "sword") or has_effect(my_snake, "sword")
    has_boost = has_token(my_snake, "boost", "speed")
    speed_active = has_effect(my_snake, "boost", "speed")
    has_stack = has_token(my_snake, "stack")
    has_star = has_token(my_snake, "star", "shield")
    star_active = has_effect(my_snake, "star", "shield")

    apples, bad_apples, stars, swords, boosts, stacks = classify_items(items)
    bad_set = set(bad_apples)

    # obstacles from main already include every snake body, including dead/corpse bodies.
    all_bodies = set(obstacles)
    enemy_bodies = all_bodies - my_body_set

    # Strict blocking for normal movement: dead bodies, enemy bodies and own body all blocked.
    blocked = set(all_bodies)
    blocked_no_self = set(all_bodies - my_body_set)

    zones = enemy_prediction(snakes, my_head, field_size)
    direct_cuts, approach_cuts = find_sword_cut_moves(my_head, snakes, blocked_no_self, zones, field_size)

    # ------------------------------------------------------
    # Build candidate moves. Never return a crash fallback.
    # ------------------------------------------------------
    clean_moves = {}
    emergency_moves = {}
    stack_moves = {}

    for move, delta in DIRECTIONS.items():
        if move == OPPOSITE.get(current_direction):
            continue
        nxt = wrap(add(my_head, delta), w, h)
        emergency_moves[move] = nxt

        # Direct sword cut can legally enter enemy body only when sword is/gets active.
        direct_sword_contact = move in direct_cuts and has_sword

        if nxt in my_body_no_head:
            if has_stack:
                stack_moves[move] = nxt
            continue

        if nxt in enemy_bodies and not (direct_sword_contact or star_active):
            # enemy/dead body collision is blocked. If it is a dead body, sword does not help.
            continue

        if nxt in zones["d1"] or nxt in zones["r1"]:
            # allow only if absolutely needed later; not a clean move.
            continue

        clean_moves[move] = nxt

    if clean_moves:
        moves_to_score = clean_moves
    elif stack_moves:
        moves_to_score = stack_moves
    else:
        # Last resort: score non-reverse moves but heavily punish deadly cells.
        moves_to_score = emergency_moves

    best_move = None
    best_score = -10**18

    center, center_r = center_region(field_size)
    center_apples = [a for a in apples if wrap_dist(a, center, w, h) <= center_r]

    for move, nxt in moves_to_score.items():
        score = 0

        # Hard collision penalties.
        if nxt in my_body_no_head:
            score -= SELF_COLLISION_PENALTY
            if has_stack:
                score += STACK_ESCAPE_REWARD
        if nxt in enemy_bodies and not (move in direct_cuts and has_sword) and not star_active:
            score -= DEAD_BODY_PENALTY

        # Speed simulation: if speed active or activating boost, both cells matter.
        path_cells = [nxt]
        if speed_active:
            path_cells = speed_path_cells(my_head, move, field_size)
        for c in path_cells:
            if c in my_body_no_head:
                score -= SELF_COLLISION_PENALTY
            if c in enemy_bodies and not (move in direct_cuts and has_sword) and not star_active:
                score -= DEAD_BODY_PENALTY
            if c in bad_set:
                score -= BAD_APPLE_PENALTY
            if c in zones["d1"] or c in zones["r1"]:
                score -= ENEMY_HEAD_1_PENALTY
            elif c in zones["d2"] or c in zones["r2"]:
                score -= ENEMY_HEAD_2_PENALTY
            elif c in zones["d3"]:
                score -= ENEMY_HEAD_3_PENALTY

        # Survival / open space. Include dead bodies as blocked.
        space_block = blocked if nxt not in my_body_no_head else blocked_no_self
        space = flood_fill(nxt, space_block, field_size)
        score += space * OPEN_SPACE_WEIGHT
        if space < max(8, len(my_body) // 2):
            score -= LOW_SPACE_PENALTY
        score += emergency_escape_score(nxt, space_block, field_size)

        # Bad apple proximity: avoid paths that brush them if alternatives exist.
        if bad_apples:
            nb = nearest_distance(nxt, bad_apples, field_size)
            if nb <= 2:
                score -= BAD_APPLE_NEAR_PENALTY * (3 - nb)

        # Direct good apple. Safe adjacent apples are very valuable.
        if nxt in apples:
            score += APPLE_REWARD
        if apples:
            safe_apples = [a for a in apples if not is_contested(a, my_head, snakes, field_size)]
            targets = safe_apples if safe_apples else apples
            # Prefer center apples when still plentiful, otherwise all apples.
            if len(center_apples) >= max(3, center_r // 2):
                targets = center_apples + targets
            best_apple_score = 0
            for a in targets:
                d = wrap_dist(nxt, a, w, h)
                val = 900 / (d + 1)
                if a in center_apples:
                    val += CENTER_APPLE_BONUS / (d + 1)
                if a in zones["d1"] or a in zones["r1"]:
                    val -= 900
                if is_contested(a, my_head, snakes, field_size):
                    val -= 250
                best_apple_score = max(best_apple_score, val)
            score += best_apple_score

        # Star: useful but not suicide-worthy. Only reward if we are strictly closer.
        for st in stars:
            my_d = wrap_dist(my_head, st, w, h)
            enemy_ds = [wrap_dist(s.get("head"), st, w, h) for s in snakes if s.get("head") and s.get("head") != my_head]
            enemy_best = min(enemy_ds) if enemy_ds else 9999
            if my_d < enemy_best:
                d = wrap_dist(nxt, st, w, h)
                score += max(0, STAR_REWARD - d * 280)
            else:
                # contested/lost star zone is risky.
                if wrap_dist(nxt, st, w, h) <= 2:
                    score -= 800

        # Valuable item pickup priority.
        for target_list, weight in ((swords, 1250), (stacks, 1150), (boosts, 900)):
            if target_list:
                d = nearest_distance(nxt, target_list, field_size)
                score += max(0, weight - d * 140)
                if nxt in target_list:
                    score += ITEM_REWARD

        # Combat: sword cuts should be aggressive but safe.
        if move in direct_cuts and has_sword:
            score += direct_cuts[move]
        if move in approach_cuts and has_sword:
            score += approach_cuts[move]

        # Star active: opportunistically touch close opponents, but not chase far.
        if star_active:
            close_enemy_body = any(wrap_dist(nxt, b, w, h) <= 1 for b in enemy_bodies)
            if close_enemy_body:
                score += 550

        # Enemy pressure: keep some distance from heads.
        for s in snakes:
            eh = s.get("head")
            if not eh or eh == my_head:
                continue
            d = wrap_dist(nxt, eh, w, h)
            if d == 1:
                score -= 3000
            elif d == 2:
                score -= 900
            else:
                score += min(d, 8) * 8

        # Avoid sword-threat exposed body paths.
        exposure = body_exposure(my_body, zones)
        if exposure:
            score -= exposure * 180

        if move == current_direction:
            score += STRAIGHT_BONUS

        if score > best_score:
            best_score = score
            best_move = move

    # If everything scored badly, select the safest non-crashing move explicitly.
    if best_move is None:
        for move, delta in DIRECTIONS.items():
            if move == OPPOSITE.get(current_direction):
                continue
            nxt = wrap(add(my_head, delta), w, h)
            if nxt not in blocked and nxt not in zones["d1"]:
                best_move = move
                break
        if best_move is None:
            best_move = current_direction

    chosen_pos = wrap(add(my_head, DIRECTIONS[best_move]), w, h)

    # ======================================================
    # ACTION DECISION
    # ======================================================
    activate = None
    stack_needed = should_stack(
        my_body,
        chosen_pos,
        blocked_no_self,
        zones,
        field_size,
        has_stack,
        bool(clean_moves),
    )

    immediate_safe_cut = best_move in direct_cuts and has_sword and _tick - _last_sword >= SWORD_COOLDOWN
    near_cut = best_move in approach_cuts and has_sword and _tick - _last_sword >= SWORD_COOLDOWN

    # Stack overrides when survival is at risk; otherwise sword is allowed to attack.
    if stack_needed and _tick - _last_stack >= STACK_COOLDOWN and not immediate_safe_cut:
        activate = "STACK"
        _last_stack = _tick
    elif immediate_safe_cut or near_cut:
        activate = "SWORD"
        _last_sword = _tick
    else:
        # Use boost/speed only when path cells are clean and it helps escape/reach item.
        if has_boost and _tick - _last_boost >= BOOST_COOLDOWN:
            p1, p2 = speed_path_cells(my_head, best_move, field_size)
            speed_safe = (
                p1 not in blocked and p2 not in blocked and
                p1 not in bad_set and p2 not in bad_set and
                p1 not in zones["d1"] and p2 not in zones["d1"]
            )
            near_value = min(
                nearest_distance(my_head, swords + stacks + stars + boosts + apples, field_size),
                9999,
            )
            danger_close = chosen_pos in zones["d2"] or escape_options(chosen_pos, blocked, field_size) <= 1
            if speed_safe and (danger_close or near_value <= 5):
                activate = "BOOST"
                _last_boost = _tick

        # Star activation if your main supports it and it is useful for crowded control.
        if activate is None and has_star and _tick - _last_star >= STAR_COOLDOWN:
            if chosen_pos in zones["d2"] or nearest_distance(my_head, list(enemy_bodies), field_size) <= 2:
                activate = "STAR"
                _last_star = _tick

    return best_move, activate
