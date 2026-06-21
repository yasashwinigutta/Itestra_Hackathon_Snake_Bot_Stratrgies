import argparse
import time

from api import SnakeFieldAPI
from strategy5 import choose_next_move


def is_valid_coord(c):
    return isinstance(c, (list, tuple)) and len(c) >= 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("team_name")
    parser.add_argument("game_name")
    parser.add_argument("--password", default="test")
    parser.add_argument("--base_url", default="http://localhost:3030")
    args = parser.parse_args()

    api = SnakeFieldAPI(
        args.base_url,
        args.team_name,
        args.game_name,
        args.password
    )

    current_direction = "NORTH"
    api.set_direction(current_direction)

    print("Bot started.")

    while True:
        time.sleep(0.5)

        field = api.get_field()
        if not field:
            continue

        snake = field.snakes.get(args.team_name)
        if not snake or not snake.alive or not snake.body:
            continue

        head = snake.body[0]

        if not is_valid_coord(head):
            continue

        my_head = (int(head[0]), int(head[1]))

        # ---------------- OBSTACLES ----------------
        obstacles = set()
        snakes_info = []

        for name, s in field.snakes.items():
            body = [(int(x), int(y)) for x, y in s.body]
            obstacles.update(body)

            snakes_info.append({
                "name": name,
                "body": body,
                "head": body[0]
            })

        # ---------------- ITEMS (FIXED) ----------------
        items = field.items

        apples = [i for i in items if i.kind == "Apple"]
        bad = [i for i in items if i.kind == "BadApple"]

        closest = None
        if apples:
            closest = min(
                apples,
                key=lambda a: abs(a.position[0] - my_head[0]) + abs(a.position[1] - my_head[1])
            )

        print(f"[DBG] A:{len(apples)} B:{len(bad)} Target:{closest.position if closest else None}")
        # ---------------- STRATEGY ----------------
        new_dir = choose_next_move(
            my_head,
            obstacles,
            snakes_info,
            field.size,
            items,
            current_direction
        )

        current_direction = new_dir
        api.set_direction(current_direction)