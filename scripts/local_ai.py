"""Run the web platform and Detective-model /detect together on localhost."""
from __future__ import annotations

import argparse
from contextlib import asynccontextmanager
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]


def prerequisites(model_dir: Path) -> list[str]:
    missing = []
    for name in (
        'src/modal_api.py',
        'outputs/onnx-stage2/rfdetr_fp32.onnx',
        'outputs/onnx-stage2/export_manifest.json',
        'weights/moondream/model.json',
    ):
        if not (model_dir / name).is_file():
            missing.append(f'파일 필요: {model_dir / name}')
    metadata = model_dir / 'weights/moondream/model.json'
    if metadata.is_file():
        try:
            if not json.loads(metadata.read_text()).get('model_id'):
                missing.append('model.json에 학습된 model_id가 필요합니다.')
        except (ValueError, OSError):
            missing.append('model.json을 읽을 수 없습니다.')
    if not os.environ.get('MOONDREAM_API_KEY', '').strip():
        missing.append('환경변수 필요: MOONDREAM_API_KEY (학습된 분류 모델 접근용)')
    for module, package in (
        ('cv2', 'opencv-python-headless'), ('onnxruntime', 'onnxruntime'),
        ('moondream', 'moondream'), ('yaml', 'PyYAML'), ('PIL', 'Pillow'),
        ('numpy', 'numpy'), ('fastapi', 'fastapi'), ('uvicorn', 'uvicorn'),
    ):
        if importlib.util.find_spec(module) is None:
            missing.append(f'Python 패키지 필요: {package}')
    return missing


def build_app(model_dir: Path, port: int):
    # Set these before importing the web backend. Keys stay in this process.
    os.environ['DG_AI_URL'] = f'http://127.0.0.1:{port}/local-ai'
    os.environ['DG_AI_KEY'] = secrets.token_urlsafe(32)
    os.environ.setdefault('DG_AI_TIMEOUT_S', '120')
    sys.path.insert(0, str(model_dir))
    sys.path.insert(0, str(ROOT))

    from fastapi import FastAPI
    from src.inference.image_inference import ImageInference
    from src.inference.onnx_detector import ONNXDetector
    from src.inference.classify_moondream import load_moondream_model
    from src.modal_api import create_modal_api
    from app import app as web

    def load_inference():
        # The deployment config requires CUDA; local Macs use ONNX CPU instead.
        detector = ONNXDetector(
            model_path=model_dir / 'outputs/onnx-stage2/rfdetr_fp32.onnx',
            provider='CPUExecutionProvider', confidence_threshold=0.3,
            intra_op_num_threads=2,
        )
        metadata = json.loads((model_dir / 'weights/moondream/model.json').read_text())
        model, tokenizer = load_moondream_model(
            model_id=metadata['model_id'], api_key=os.environ['MOONDREAM_API_KEY'],
        )
        return ImageInference(detector, model, tokenizer)

    ai = create_modal_api(
        api_key=os.environ['DG_AI_KEY'], inference_loader=load_inference,
        # Browsers use the authenticated web proxy; no direct browser CORS is needed.
        cors_origin='https://localhost',
    )

    @asynccontextmanager
    async def lifespan(application):
        # Mounted apps do not automatically run their lifespan handlers.
        async with ai.router.lifespan_context(ai):
            async with web.router.lifespan_context(web):
                yield

    application = FastAPI(lifespan=lifespan)
    application.mount('/local-ai', ai)
    application.mount('/', web)
    return application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', type=Path, default=ROOT / 'local-model/Detective-model')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--check', action='store_true', help='Check prerequisites without starting')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.exit(1, 'Python 3.10 이상을 사용하세요.\n')
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    model_dir = args.model_dir.resolve()
    missing = prerequisites(model_dir)
    if missing:
        parser.exit(1, '로컬 AI 실행 준비가 필요합니다:\n' + '\n'.join(f'- {item}' for item in missing) + '\n')
    if args.check:
        print('로컬 AI 실행 준비 확인 완료 (모델 로딩·추론은 실행 시 확인).')
        return
    import uvicorn
    application = build_app(model_dir, args.port)
    print(f'웹: http://127.0.0.1:{args.port} — 로그인 후 카메라 연결 · AI 분석')
    uvicorn.run(application, host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
