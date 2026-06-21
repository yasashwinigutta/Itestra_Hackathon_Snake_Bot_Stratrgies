from dataclasses import dataclass
from typing import Dict, List, Tuple, Any

Coord = Tuple[int, int]
TeamName = str


@dataclass
class ActiveEffectInfo:
    effect: str
    remaining_ticks: int


@dataclass
class SnakeInfo:
    body: List[Coord]
    alive: bool
    inventory: List[str]
    active_effects: List[ActiveEffectInfo]


@dataclass
class Item:
    position: Coord
    kind: str


def parse_coordinate(c: Any) -> Coord:
    try:
        if c is None:
            return (0, 0)

        if isinstance(c, dict):
            return (int(c.get("x", 0)), int(c.get("y", 0)))

        if isinstance(c, (list, tuple)) and len(c) >= 2:
            x, y = c[0], c[1]

            if isinstance(x, (list, tuple)):
                x = x[0]
            if isinstance(y, (list, tuple)):
                y = y[0]

            return (int(float(x)), int(float(y)))

    except Exception:
        pass

    return (0, 0)


def fill_snakes(source: dict) -> Dict[TeamName, SnakeInfo]:
    snakes = {}

    for team, info in source.items():
        if not isinstance(info, dict):
            continue

        body = [parse_coordinate(seg) for seg in info.get("body", []) if seg]

        effects = []
        for e in info.get("active_effects", []):
            if isinstance(e, dict):
                effects.append(
                    ActiveEffectInfo(
                        effect=str(e.get("effect", "")),
                        remaining_ticks=int(e.get("remaining_ticks", 0))
                    )
                )

        snakes[team] = SnakeInfo(
            body=body,
            alive=bool(info.get("alive", False)),
            inventory=list(info.get("inventory", [])),
            active_effects=effects,
        )

    return snakes


@dataclass
class Field:
    size: Tuple[int, int]
    snakes: Dict[TeamName, SnakeInfo]
    items: List[Item]

    @staticmethod
    def from_dict(raw: dict) -> "Field":
        if not isinstance(raw, dict):
            return Field((0, 0), {}, [])

        size = (20, 20)
        if isinstance(raw.get("size"), (list, tuple)) and len(raw["size"]) >= 2:
            size = (int(raw["size"][0]), int(raw["size"][1]))

        snakes = fill_snakes(raw.get("snake", raw.get("snakes", {})))

        items: List[Item] = []

        for it in raw.get("items", []):
            if not isinstance(it, (list, tuple)) or len(it) < 2:
                continue

            pos = parse_coordinate(it[0])
            kind = str(it[1])

            if pos != (0, 0):
                items.append(Item(position=pos, kind=kind))

        return Field(size=size, snakes=snakes, items=items)