#!/usr/bin/env python3
"""build_yolo_dataset.py — 把 HSR 截屏 + labelImg 标注转为 COCO 格式.

**一次性脚本**：不在 src/ 下，不需要测试。

用法：
    1. 截屏到 data/yolo/raw_frames/*.png（手动截 200+ 帧）
    2. 用 labelImg 标注（XML 保存到 data/yolo/annotations/）
    3. 运行此脚本：
        uv run python scripts/build_yolo_dataset.py
    4. 输出 data/yolo/annotations.json（COCO 格式）

类别（与 screen.detector.DEFAULT_HSR_LABELS 对齐）：
    0: character_portrait
    1: enemy
    2: buff_icon
    3: debuff_icon
    4: ultimate_ready
    5: cycle_counter
    6: enemy_hp_bar
    7: character_hp_bar
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

LABEL_MAP = {
    "character_portrait": 0,
    "enemy": 1,
    "buff_icon": 2,
    "debuff_icon": 3,
    "ultimate_ready": 4,
    "cycle_counter": 5,
    "enemy_hp_bar": 6,
    "character_hp_bar": 7,
}


def parse_xml(xml_path: Path) -> Dict[str, Any]:
    """解析 labelImg 的 VOC XML."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size = root.find("size")
    width = int(size.find("width").text)
    height = int(size.find("height").text)

    boxes: List[Dict[str, Any]] = []
    for obj in root.findall("object"):
        name = obj.find("name").text
        if name not in LABEL_MAP:
            print(f"  跳过未知类别: {name}", file=sys.stderr)
            continue
        bnd = obj.find("bndbox")
        xmin = int(bnd.find("xmin").text)
        ymin = int(bnd.find("ymin").text)
        xmax = int(bnd.find("xmax").text)
        ymax = int(bnd.find("ymax").text)
        boxes.append(
            {
                "category_id": LABEL_MAP[name],
                "bbox": [xmin, ymin, xmax - xmin, ymax - ymin],
                "area": (xmax - xmin) * (ymax - ymin),
            }
        )

    filename = root.find("filename").text
    return {"file_name": filename, "width": width, "height": height, "boxes": boxes}


def build_coco(
    frames_dir: Path, annotations_dir: Path, output_path: Path
) -> int:
    """组装 COCO 格式 JSON."""
    coco: Dict[str, Any] = {
        "info": {
            "description": "HSR UI Detection Dataset",
            "version": "1.0",
            "date_created": datetime.now().isoformat(),
        },
        "licenses": [],
        "categories": [
            {"id": v, "name": k, "supercategory": "hsr_ui"}
            for k, v in LABEL_MAP.items()
        ],
        "images": [],
        "annotations": [],
    }

    annotation_id = 1
    image_id = 1
    total_boxes = 0

    for xml_path in sorted(annotations_dir.glob("*.xml")):
        parsed = parse_xml(xml_path)
        image_entry = {
            "id": image_id,
            "file_name": parsed["file_name"],
            "width": parsed["width"],
            "height": parsed["height"],
        }
        coco["images"].append(image_entry)

        for box in parsed["boxes"]:
            coco["annotations"].append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": box["category_id"],
                    "bbox": box["bbox"],
                    "area": box["area"],
                    "iscrowd": 0,
                }
            )
            annotation_id += 1
            total_boxes += 1

        image_id += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(coco, ensure_ascii=False, indent=2))
    return total_boxes


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 labelImg 标注的 VOC XML 转 COCO 格式"
    )
    parser.add_argument(
        "--frames",
        type=Path,
        default=Path("data/yolo/raw_frames"),
        help="截屏 PNG 目录",
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        default=Path("data/yolo/annotations"),
        help="labelImg XML 目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/yolo/annotations.json"),
        help="输出 COCO JSON",
    )
    args = parser.parse_args()

    if not args.annotations.exists():
        print(f"错误：标注目录不存在: {args.annotations}", file=sys.stderr)
        print(
            "请先用 labelImg 标注截屏，XML 保存到该目录",
            file=sys.stderr,
        )
        return 1

    n_boxes = build_coco(args.frames, args.annotations, args.output)
    print(f"✅ 转换完成: {args.output}")
    print(f"   图像数: {len(list(args.annotations.glob('*.xml')))}")
    print(f"   标注框数: {n_boxes}")
    print(f"   类别数: {len(LABEL_MAP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())