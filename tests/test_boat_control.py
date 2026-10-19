from backend.app.routers.boat import BoatControl, Pose


def pose(yaw=0, x=0, tx=10):
    return Pose(x=x, y=0, yaw_deg=yaw, target_x=tx, target_y=0)


def test_pid_and_derivative():
    c = BoatControl()
    assert c.guidance(pose(-10), 1)["rudder"] == 8
    assert c.guidance(pose(-12), 1.1)["rudder"] == 12.6
    assert c.guidance(pose(-100), 1.2)["rudder"] == 35


def test_emergency_stop_survives_pose_and_requires_fresh_pose_after_clear():
    c = BoatControl()
    c.guidance(pose(), 1)
    c.emergency_stop()
    assert c.guidance(pose(x=10), 2) == dict(throttle=0, rudder=0, net=None, estop=True)
    c.clear_estop()
    assert c.read(2)["throttle"] == 0
    assert c.guidance(pose(), 3)["throttle"] == 35


def test_arrival_and_stale_pose():
    c = BoatControl()
    assert c.guidance(pose(x=10), 1)["net"] == 150
    assert c.guidance(pose(), 2)["net"] is None
    assert c.read(3.6) == dict(throttle=0, rudder=0, net=None, estop=False)


def test_wrapped_derivative():
    c = BoatControl()
    c.guidance(pose(-179), 1)
    assert c.guidance(pose(179), 1.1)["rudder"] == -35
