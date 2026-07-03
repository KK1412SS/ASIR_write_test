from dataclasses import dataclass


@dataclass
class SafetyBounds:
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


def is_position_in_bounds(x: float, y: float, z: float, bounds: SafetyBounds) -> bool:
    return (
        bounds.x_min <= x <= bounds.x_max and
        bounds.y_min <= y <= bounds.y_max and
        bounds.z_min <= z <= bounds.z_max
    )


def check_position_or_raise(x: float, y: float, z: float, bounds: SafetyBounds):
    if not is_position_in_bounds(x, y, z, bounds):
        raise ValueError(
            f"Unsafe target position: x={x:.4f}, y={y:.4f}, z={z:.4f} "
            f"not in bounds "
            f"[x: {bounds.x_min:.4f}..{bounds.x_max:.4f}, "
            f"y: {bounds.y_min:.4f}..{bounds.y_max:.4f}, "
            f"z: {bounds.z_min:.4f}..{bounds.z_max:.4f}]"
        )


def find_first_invalid_robot_position(points, bounds: SafetyBounds):
    """
    points: list of [robot_y, robot_x, robot_z]
    returns: (index, point) or (None, None)
    """
    for i, p in enumerate(points):
        robot_y, robot_x, robot_z = p
        if not is_position_in_bounds(robot_x, robot_y, robot_z, bounds):
            return i, p
    return None, None