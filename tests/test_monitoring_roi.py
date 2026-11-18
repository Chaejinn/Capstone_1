import unittest
from pydantic import ValidationError
from backend.platform.camera_configuration import MonitoringROI

class MonitoringRoiTests(unittest.TestCase):
    def setUp(self):self.roi=MonitoringROI(points=[{'x':25,'y':25},{'x':75,'y':25},{'x':75,'y':75},{'x':25,'y':75}])
    def test_box_center_and_boundary(self):
        self.assertTrue(self.roi.includes_bbox([40,40,60,60],[100,100]))
        self.assertFalse(self.roi.includes_bbox([0,0,40,40],[100,100]))
        self.assertTrue(self.roi.includes_bbox([20,40,30,60],[100,100]))
    def test_default_square_tracks_image_aspect(self):
        for width,height in ((1280,720),(720,1280)):
            p=MonitoringROI().polygon_for_size(width,height)
            self.assertAlmostEqual((p[1][0]-p[0][0])*width/100,min(width,height)*.88)
            self.assertAlmostEqual((p[3][1]-p[0][1])*height/100,min(width,height)*.88)
    def test_invalid_polygons_rejected(self):
        for points in ([{'x':0,'y':0}]*3,[{'x':0,'y':0},{'x':100,'y':100}],
                       [{'x':0,'y':0},{'x':50,'y':50},{'x':100,'y':100}]):
            with self.assertRaises(ValidationError):MonitoringROI(points=points)
    def test_concave_polygon(self):
        roi=MonitoringROI(points=[{'x':10,'y':10},{'x':90,'y':10},{'x':50,'y':50},{'x':90,'y':90},{'x':10,'y':90}])
        self.assertFalse(roi.includes_bbox([75,45,85,55],[100,100]))
        self.assertTrue(roi.includes_bbox([15,45,25,55],[100,100]))
