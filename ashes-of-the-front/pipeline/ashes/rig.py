"""Rig checks: hierarchy, attachments, draw order, constraints and mesh deformation."""

from __future__ import annotations

from .report import Report

WEIGHT_TOLERANCE = 1e-3


def validate_rig(rig: dict, label: str, layer_names: set[str], report: Report) -> None:
    bones = rig["bones"]
    names = [bone["name"] for bone in bones]
    for name in sorted({n for n in names if names.count(n) > 1}):
        report.error(f"{label}: duplicate bone name '{name}'")
    parents = {bone["name"]: bone["parent"] for bone in bones}

    roots = [name for name, parent in parents.items() if parent is None]
    if len(roots) != 1:
        report.error(f"{label}: rig must have exactly one root bone, found {len(roots)}")
    for name, parent in parents.items():
        if parent is not None and parent not in parents:
            report.error(f"{label}: bone '{name}' has missing parent '{parent}'")
    _check_cycles(parents, label, report)

    attached: set[str] = set()
    for attachment in rig["attachments"]:
        layer, bone = attachment["layer"], attachment["bone"]
        if layer not in layer_names:
            report.error(f"{label}: attachment on bone '{bone}' references missing sprite '{layer}' (not a layer in asset.json)")
        elif layer in attached:
            report.error(f"{label}: layer '{layer}' is attached more than once")
        attached.add(layer)
        if bone not in parents:
            report.error(f"{label}: attachment '{layer}' uses unknown bone '{bone}'")

    order = rig["draw_order"]
    for layer in sorted({n for n in order if order.count(n) > 1}):
        report.error(f"{label}: draw_order lists '{layer}' more than once")
    for layer in sorted(set(order) - attached):
        report.error(f"{label}: draw_order lists '{layer}', which has no attachment")
    for layer in sorted(attached - set(order)):
        report.error(f"{label}: attachment '{layer}' is missing from draw_order")

    _check_constraints(rig["constraints"], parents, label, report)
    _check_deform(rig["deform"], attached, parents, label, report)


def _check_cycles(parents: dict[str, str | None], label: str, report: Report) -> None:
    reported: set[frozenset[str]] = set()
    for start in parents:
        path: list[str] = []
        seen: set[str] = set()
        current: str | None = start
        while current is not None and current in parents:
            if current in seen:
                loop = path[path.index(current):] + [current]
                key = frozenset(loop)
                if key not in reported:
                    reported.add(key)
                    report.error(f"{label}: circular bone hierarchy: {' -> '.join(loop)}")
                break
            seen.add(current)
            path.append(current)
            current = parents[current]


def _check_constraints(constraints: list[dict], parents: dict, label: str, report: Report) -> None:
    names = [c["name"] for c in constraints]
    for name in sorted({n for n in names if names.count(n) > 1}):
        report.error(f"{label}: duplicate constraint name '{name}'")
    for constraint in constraints:
        name, bones = constraint["name"], constraint["bones"]
        for bone in bones:
            if bone not in parents:
                report.error(f"{label}: constraint '{name}' references unknown bone '{bone}'")
        if constraint["type"] == "ik":
            if len(bones) != 2:
                report.error(f"{label}: IK constraint '{name}' needs exactly two bones [upper, lower]")
            elif parents.get(bones[1]) != bones[0]:
                report.error(
                    f"{label}: IK constraint '{name}' chain is not parent-to-child: "
                    f"'{bones[0]}' must be the parent of '{bones[1]}'"
                )
            target = constraint.get("target")
            if target is None:
                report.error(f"{label}: IK constraint '{name}' needs a target bone")
            elif target not in parents:
                report.error(f"{label}: IK constraint '{name}' targets unknown bone '{target}'")
            elif target in bones:
                report.error(f"{label}: IK constraint '{name}' target '{target}' is inside its own chain")
        else:
            if len(bones) != 1:
                report.error(f"{label}: rotation_limit '{name}' needs exactly one bone")
            if "min" not in constraint or "max" not in constraint:
                report.error(f"{label}: rotation_limit '{name}' needs both min and max")
            elif constraint["min"] > constraint["max"]:
                report.error(f"{label}: rotation_limit '{name}' has min greater than max")


def _check_deform(deform: list[dict], attached: set[str], parents: dict, label: str, report: Report) -> None:
    for mesh in deform:
        layer = mesh["layer"]
        if layer not in attached:
            report.error(f"{label}: deform for '{layer}' needs that layer to be attached to a bone")
        if len(mesh["vertices"]) != len(mesh["influences"]):
            report.error(
                f"{label}: deform '{layer}' has {len(mesh['vertices'])} vertices "
                f"but {len(mesh['influences'])} influence lists"
            )
        for index, influences in enumerate(mesh["influences"]):
            if not influences:
                report.error(f"{label}: deform '{layer}' vertex {index} has no bone influence")
                continue
            for influence in influences:
                if influence["bone"] not in parents:
                    report.error(f"{label}: deform '{layer}' vertex {index} uses unknown bone '{influence['bone']}'")
            total = sum(influence["weight"] for influence in influences)
            if abs(total - 1) > WEIGHT_TOLERANCE:
                report.error(f"{label}: deform '{layer}' vertex {index} weights sum to {total:.3f}, expected 1")
