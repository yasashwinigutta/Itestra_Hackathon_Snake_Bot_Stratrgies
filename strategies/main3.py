import argparse
import time

from api import SnakeFieldAPI
from strategyStack_Y1 import choose_next_move


DIRECTION_FALLBACK = "NORTH"


def is_valid_coord(c):
    return isinstance(c, (list, tuple)) and len(c) >= 2


def norm_coord(c):
    return (int(c[0]), int(c[1]))


def effect_to_dict(effect):
    """Make active effects easy for the strategy to inspect.

    Field.py stores effects as ActiveEffectInfo(effect, remaining_ticks), but
    older strategy versions sometimes expect strings/dicts. This keeps both safe.
    """
    try:
        return {
            "effect": str(getattr(effect, "effect", "")),
            "remaining_ticks": int(getattr(effect, "remaining_ticks", 0)),
        }
    except Exception:
        return {"effect": str(effect), "remaining_ticks": 0}


def find_inventory_item(inventory, keywords, fallback):
    """Return the exact inventory token to activate, if present.

    The server may use names like "Speed Boost", "Stack", "Sword", etc.
    Activating the exact token from inventory is safer than hardcoding.
    """
    keywords = [k.lower() for k in keywords]
    for item in inventory or []:
        text = str(item).lower()
        if any(k in text for k in keywords):
            return item
    return fallback


def activate_requested_item(api, snake, activate):
    """Translate strategy activation strings into API activate_item calls."""
    if not activate:
        return

    inventory = list(getattr(snake, "inventory", []) or [])

    if activate is True:
        # Backward compatibility with old strategies.
        item_to_send = find_inventory_item(
            inventory,
            ["speed", "boost", "stack", "sword"],
            "Speed Boost",
        )
        print(f"[ACTION] activate generic -> {item_to_send}")
        api.activate_item(item_to_send)
        return

    if not isinstance(activate, str):
        return

    action = activate.upper().strip()

    if action == "SWORD":
        item_to_send = find_inventory_item(inventory, ["sword"], "Sword")
    elif action in ("BOOST", "SPEED"):
        # Strategy may say BOOST, but inventory/server may call it Speed Boost.
        item_to_send = find_inventory_item(inventory, ["speed", "boost"], "Speed Boost")
    elif action == "STACK":
        item_to_send = find_inventory_item(inventory, ["stack"], "Stack")
    elif action in ("STAR", "SHIELD"):
        item_to_send = find_inventory_item(inventory, ["star", "shield"], "Star")
    else:
        # Last-resort fallback: pass through the requested item name.
        item_to_send = activate

    print(f"[ACTION] activate {action} -> {item_to_send}")
    api.activate_item(item_to_send)


def main():
    parser = argparse.ArgumentParser(description="Snake bot client")
    parser.add_argument("team_name")
    parser.add_argument("game_name")
    parser.add_argument("--password", default="test")
    parser.add_argument("--base_url", default="http://localhost:3030")
    args = parser.parse_args()

    api = SnakeFieldAPI(
        args.base_url,
        args.team_name,
        args.game_name,
        args.password,
    )

    current_direction = DIRECTION_FALLBACK
    api.set_direction(current_direction)

    print("Bot started with Stack-Safe Combat Survival Strategy.")

    tick = 0

    while True:
        time.sleep(0.5)
        tick += 1

        field = api.get_field()
        if not field:
            continue

        snake = field.snakes.get(args.team_name)
        if not snake or not snake.alive or not snake.body:
            continue

        head = snake.body[0]
        if not is_valid_coord(head):
            continue

        my_head = norm_coord(head)

        # ---------------- OBSTACLES + SNAKE INFO ----------------
        obstacles = set()
        snakes_info = []

        for name, s in field.snakes.items():
            if not getattr(s, "body", None):
                continue

            body = [norm_coord(seg) for seg in s.body if is_valid_coord(seg)]
            if not body:
                continue

            obstacles.update(body)

            snakes_info.append({
                "name": name,
                "body": body,
                "head": body[0],
                "inventory": list(getattr(s, "inventory", []) or []),
                "active_effects": [
                    effect_to_dict(e)
                    for e in (getattr(s, "active_effects", []) or [])
                ],
                "alive": bool(getattr(s, "alive", False)),
                "body_no_head": body[1:] if len(body) > 1 else [],
            })

        # ---------------- ITEMS ----------------
        items = field.items
        item_kinds = [str(getattr(i, "kind", "")).lower() for i in items]

        print(
            f"[DBG] tick={tick} "
            f"A:{sum('apple' in k and 'bad' not in k for k in item_kinds)} "
            f"B:{sum('bad' in k for k in item_kinds)} "
            f"Sword:{sum('sword' in k for k in item_kinds)} "
            f"Speed:{sum('speed' in k or 'boost' in k for k in item_kinds)} "
            f"Stack:{sum('stack' in k for k in item_kinds)} "
            f"Star:{sum('star' in k or 'shield' in k for k in item_kinds)} "
            f"Inv:{list(getattr(snake, 'inventory', []) or [])}"
        )

        # ---------------- STRATEGY ----------------
        try:
            new_dir, activate = choose_next_move(
                my_head,
                obstacles,
                snakes_info,
                field.size,
                items,
                current_direction,
            )
        except Exception as e:
            print("[ERROR] strategy failed:", e)
            new_dir, activate = current_direction, None

        # ---------------- ITEM ACTIVATION ----------------
        try:
            activate_requested_item(api, snake, activate)
        except Exception as e:
            print("[ERROR] item activation failed:", e)

        # ---------------- MOVE UPDATE ----------------
        if new_dir not in ("NORTH", "SOUTH", "EAST", "WEST"):
            new_dir = current_direction

        current_direction = new_dir

        try:
            api.set_direction(current_direction)
        except Exception as e:
            print("[ERROR] direction update failed:", e)


if __name__ == "__main__":
    main()
