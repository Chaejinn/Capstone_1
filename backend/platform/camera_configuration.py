"""Validated camera configuration contract shared by Vercel and the CPU vision service."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
import numpy as np

DICTIONARY_COUNTS = {'DICT_4X4_50':50, 'DICT_5X5_100':100, 'DICT_6X6_250':250}


class Point(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: float = Field(ge=0,le=100)
    y: float = Field(ge=0,le=100)


class Homography(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    enabled: StrictBool = False
    image_points: list[Point] = Field(default_factory=list,max_length=4)
    image_size: tuple[int,int] | None = None
    pool_width_m: float | None = Field(default=None,gt=0,le=10000)
    pool_height_m: float | None = Field(default=None,gt=0,le=10000)
    frame_id: str = Field(default='pool-01',min_length=1,max_length=80)
    calibration_id: str | None = Field(default=None,max_length=80)

    @model_validator(mode='after')
    def geometry(self):
        if self.image_size is not None and any(not 2<=v<=16384 for v in self.image_size):
            raise ValueError('영상 크기가 올바르지 않습니다.')
        if not self.enabled and not self.image_points:return self
        if len(self.image_points)!=4:
            raise ValueError('좌상·우상·우하·좌하 순서로 4점을 지정하세요.')
        p=np.array([[v.x,v.y] for v in self.image_points])
        edges=np.roll(p,-1,axis=0)-p
        cross=edges[:,0]*np.roll(edges,-1,axis=0)[:,1]-edges[:,1]*np.roll(edges,-1,axis=0)[:,0]
        area=.5*np.sum(p[:,0]*np.roll(p[:,1],-1)-np.roll(p[:,0],-1)*p[:,1])
        if len(np.unique(p,axis=0))!=4 or not np.all(cross>1e-6) or area<100:
            raise ValueError('4점은 화면 기준 시계 방향의 볼록 사각형이어야 합니다 (영상 면적 1% 이상).')
        if self.enabled and (self.image_size is None or self.pool_width_m is None or self.pool_height_m is None):
            raise ValueError('영상 크기와 실측 수조 너비·높이가 필요합니다.')
        return self


class Aruco(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    enabled: StrictBool = False
    dictionary: Literal['DICT_4X4_50','DICT_5X5_100','DICT_6X6_250'] = 'DICT_4X4_50'
    marker_id: int = Field(default=0,ge=0,strict=True)
    marker_size_m: float = Field(default=.05,gt=0,le=5)
    heading_offset_deg: float | None = Field(default=None,ge=-180,le=180)
    heading_measured: StrictBool = False

    @model_validator(mode='after')
    def marker(self):
        if self.marker_id>=DICTIONARY_COUNTS[self.dictionary]:raise ValueError('선택한 사전에 없는 마커 ID입니다.')
        if self.heading_measured and self.heading_offset_deg is None:raise ValueError('측정한 헤딩 오프셋을 입력하세요.')
        return self


class CameraConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(default=0,ge=0)
    homography: Homography = Field(default_factory=Homography)
    aruco: Aruco = Field(default_factory=Aruco)


def calibration_dict(homography, image_size):
    """Normalize full-image percentages to the actual resized upload dimensions."""
    h=homography if isinstance(homography,Homography) else Homography.model_validate(homography)
    if not h.enabled:return {}
    w,hei=image_size
    oldw,oldh=h.image_size
    if abs((w/hei)/(oldw/oldh)-1)>.01:raise ValueError('IMAGE_ASPECT_MISMATCH')
    points=[[p.x*w/100,p.y*hei/100] for p in h.image_points]
    return {'image_points':points,'world_points':[[0,h.pool_height_m],[h.pool_width_m,h.pool_height_m],
        [h.pool_width_m,0],[0,0]],'image_size':[w,hei],'world_bounds':[0,0,h.pool_width_m,h.pool_height_m],
        'frame_id':h.frame_id,'calibration_id':h.calibration_id or 'web-calibration',
        'unit':'m','origin':'physical lower-left corner','x_axis':'physical right','y_axis':'physical up',
        'bbox_anchor':[.5,1.0],'max_error_m':.05,'roi':points,'exclude_outside_roi':True}
