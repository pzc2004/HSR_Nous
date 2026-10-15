# 屏幕识别设置指南

本文档说明 HSR_Nous 屏幕识别模块 (`src/hsr_nous/screen/`) 的安装、训练、与接入流程。

## 1. 安装依赖

```bash
uv pip install mss onnxruntime
```

PaddleOCR（可选，用于识别文字 + 数字）：

```bash
uv pip install paddleocr
```

**不要**安装 `ultralytics` —— 它是 AGPL-3.0 默认许可证。本项目使用 RT-DETR-r18（Apache-2.0）。

## 2. 模块概览

```
src/hsr_nous/screen/
├── __init__.py       # 公开 API
├── capture.py        # mss 截屏
├── detector.py       # Detector 抽象 + StubDetector + OnnxDetector
├── state_parser.py   # ScreenSnapshot → sim_schema.Encounter
└── models.py         # BBox / Detection / ScreenSnapshot
```

## 3. 默认行为（无模型时）

```python
from hsr_nous.screen import get_default_detector, is_screen_enabled, capture_frame

if is_screen_enabled():
    det = get_default_detector()
    if not det.is_ready():
        print("未加载 ONNX 模型，detector.detect() 将返回空")
    frame = capture_frame()  # numpy RGB
    detections = det.detect(frame)
```

无 ONNX 模型权重时 `get_default_detector()` 返回 `StubDetector`，`detect()` 始终返回空列表。

## 4. 训练 RT-DETR-r18 检测 HSR UI

### 4.1 数据准备

用 `scripts/build_yolo_dataset.py` 把游戏截图转 COCO 格式：

```bash
# 截屏（需在游戏窗口运行时手动截 200+ 帧）
mkdir -p data/yolo/raw_frames
# ... 用 macOS `screencapture` 或 Windows Snipping Tool 截 200+ 帧 ...

# 标注：用 labelImg (https://github.com/heartexlabs/labelImg) 或 Roboflow
# 类别（与 DEFAULT_HSR_LABELS 对齐）：
#   character_portrait, enemy, buff_icon, debuff_icon,
#   ultimate_ready, cycle_counter, enemy_hp_bar, character_hp_bar

# 导出为 COCO JSON 后放到 data/yolo/annotations.json
```

### 4.2 训练

```bash
uv pip install torch torchvision  # GPU 版本请参考 PyTorch 官网
git clone https://github.com/lyu-chen/RT-DETR.git
cd RT-DETR
# 改 config：模型 r18，类别数 8，学习率 1e-4
python tools/train.py -c configs/rtdetr/rtdetr_r18_hsr.yml
```

### 4.3 导出 ONNX

```bash
python tools/export_onnx.py -c configs/rtdetr/rtdetr_r18_hsr.yml --weights output/rtdetr_r18_hsr/best.pth
```

把导出的 `rtdetr_r18_hsr.onnx` 放到：

```
data/yolo/rtdetr_r18.onnx
```

## 5. 接入（自动检测）

模型放好后，`get_default_detector()` 自动选择 `OnnxDetector`，无需改代码。

环境变量可覆盖路径：

```bash
export HSR_NOUS_YOLO_MODEL=/path/to/your/model.onnx
```

## 6. OCR 接入（PaddleOCR）

`state_parser.parse_state()` 当前假设 `Detection.text` 已由上游填充。
如需 OCR：

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=False, lang="ch")
result = ocr.ocr(frame, cls=False)
# 把识别到的文字 + 位置映射到 Detection
```

完整 OCR 集成建议作为 `OnnxDetector.detect()` 的后处理步骤，写一个 `OcrEnhancedDetector` 子类。

## 7. 已知限制

- **OCR 性能**：PaddleOCR 在 macOS ARM 上较慢（首次加载 ~10s）
- **检测器训练数据**：HSR 没有公开数据集，需自行标注 ~200 帧
- **屏幕坐标**：默认 1920×1080；其它分辨率需重新训练或做 letterbox 适配

## 8. 测试

```bash
uv run pytest tests/test_screen.py -v
```

覆盖：
- StubDetector 返回空
- OnnxDetector 在模型缺失时回退 stub
- get_default_detector 默认返回 stub
- parse_state 提取角色/敌人/轮次/buff
- snapshot_to_encounter 端到端组装
- mss 不可用时 is_screen_enabled 返回 False

## 9. 调试

```python
from hsr_nous.screen import capture_frame
frame = capture_frame()
print(f"shape: {frame.shape}")  # (1080, 1920, 3)
# 用 PIL / OpenCV 保存到本地查看
import PIL.Image
PIL.Image.fromarray(frame).save("/tmp/debug.png")
```