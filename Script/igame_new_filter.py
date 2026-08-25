#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iGameVis Filter 骨架生成器（方法 A：算法直接写在 Execute() 里）

作用：把"开发一个新 Filter"中永远不变的通用骨架（I_OBJECT 宏、New()、
     构造函数声明端口、Execute() 的取输入/校验/造输出/Modified/SetOutput）
     自动生成，只把"算法替换区"留成带 TODO 标记的空位，由你手写。

用法示例：
  # 生成 hw6 极小曲面 filter（输入/输出都是表面网格，带 3 个参数）
  python Script\\igame_new_filter.py ^
      --name MinimalSurfaceFilter ^
      --dir iGameCore\\Filters\\FeatureExtraction ^
      --input-type surface_mesh --output-type surface_mesh ^
      --param maxIter:int:1000 --param eps:float:1e-5 --param keepBoundary:bool:true ^
      --qt

  # 生成一个从点集生成网格的 filter（输出新建，不复用输入）
  python Script\\igame_new_filter.py --name MyGeneratorFilter ^
      --input-type point_set --output-type surface_mesh --mode generate

生成两个文件：<输出目录>/iGame<Name>.h 与 iGame<Name>.cpp。
新文件自动被 iGameCore 的 GLOB_RECURSE 收录，无需改 CMake。

安全性：输出目录必须已存在且位于本项目 iGameCore/Filters 内（脚本不会自动建目录）；
       若 iGameFilterIncludes.h 不存在，脚本报错并中止，不会强行追加 include。
       所有校验通过后才会写文件；任一步失败都会返回非零退出码。
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# iGameVis 类型表：CLI 类型名 -> (类名, 头文件名, 是否需要 DynamicCast)
# ---------------------------------------------------------------------------
TYPE_MAP = {
    "data_object":        ("DataObject",        "iGameDataObject.h",        False),
    "point_set":          ("PointSet",          "iGamePointSet.h",          True),
    "surface_mesh":       ("SurfaceMesh",       "iGameSurfaceMesh.h",       True),
    "unstructured_mesh":  ("UnstructuredMesh",  "iGameUnstructuredMesh.h",  True),
    "volume_mesh":        ("VolumeMesh",        "iGameVolumeMesh.h",        True),
    "structured_mesh":    ("StructuredMesh",    "iGameStructuredMesh.h",    True),
}

PARAM_TYPES = {"int", "float", "double", "bool", "string"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成 iGameVis Filter 骨架（方法 A：算法写在 Execute() 内）。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--name", required=True,
                        help="Filter 类名，如 MinimalSurfaceFilter（文件自动加 iGame 前缀）")
    parser.add_argument("--dir", default=None,
                        help="输出目录（默认: iGameCore/Filters；必须已存在且位于本项目 Filters 内）")
    parser.add_argument("--input-type", default="surface_mesh",
                        choices=sorted(TYPE_MAP),
                        help="输入数据类型（默认 surface_mesh）")
    parser.add_argument("--output-type", default="surface_mesh",
                        choices=sorted(TYPE_MAP),
                        help="输出数据类型（默认 surface_mesh）")
    parser.add_argument("--param", action="append", default=[],
                        metavar="NAME:TYPE[:DEFAULT]",
                        help="算法参数，可重复；如 maxIter:int:1000、eps:float:1e-5、"
                             "keepBoundary:bool:true")
    parser.add_argument("--inputs", type=int, default=1, help="输入端口数（默认 1）")
    parser.add_argument("--outputs", type=int, default=1, help="输出端口数（默认 1）")
    parser.add_argument("--mode", choices=["copy", "generate"], default="copy",
                        help="copy: 输出=输入深拷贝后修改（默认）；generate: 输出=新建对象")
    parser.add_argument("--qt", action="store_true",
                        help="同时打印 Qt 菜单接线示例（igQtMainWindow 用）")
    parser.add_argument("--title", default=None,
                        help="Qt 菜单/对话框显示名（默认用类名；中文标题请自行加 QStringLiteral 转义）")
    parser.add_argument("--update-includes", action=argparse.BooleanOptionalAction, default=True,
                        help="把生成的头文件追加到 iGameCore/Filters/iGameFilterIncludes.h（默认开启；"
                             "找不到该文件会报错中止，可用 --no-update-includes 关闭）")
    parser.add_argument("--force", action="store_true",
                        help="覆盖已存在的同名文件")
    return parser.parse_args()


def sanitize_identifier(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        sys.exit(f"[错误] 类名不是合法 C++ 标识符: {name!r}")
    return name


def parse_params(specs: list[str]) -> list[tuple[str, str, str, str]]:
    """返回 [(name, type, default_cpp, default_raw)]：
    default_cpp 为 C++ 侧规范化后的默认值（float 自动加 f）；
    default_raw 为用户输入的原始默认值（Qt 参数框用）。"""
    params: list[tuple[str, str, str, str]] = []
    for spec in specs:
        parts = spec.split(":")
        if len(parts) < 2 or len(parts) > 3:
            sys.exit(f"[错误] 参数格式应为 NAME:TYPE[:DEFAULT]，收到: {spec!r}")
        name, ptype = parts[0], parts[1]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            sys.exit(f"[错误] 参数名不是合法标识符: {name!r}")
        if ptype not in PARAM_TYPES:
            sys.exit(f"[错误] 不支持的参数类型 {ptype!r}（可选: {', '.join(sorted(PARAM_TYPES))}）")
        default_raw = parts[2] if len(parts) == 3 else ""
        default = default_raw
        # 规范化默认值
        if ptype == "int":
            if default == "":
                default = "0"
            try:
                int(default)
            except ValueError:
                sys.exit(f"[错误] 参数 {name} 的默认值 {default!r} 不是整数")
        elif ptype == "float":
            if default == "":
                default = "0.f"
            elif re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", default) and not default.endswith("f"):
                default += "f"
        elif ptype == "double":
            if default == "":
                default = "0.0"
        elif ptype == "bool":
            if default in ("", "true", "1"):
                default = "true"
            elif default in ("false", "0"):
                default = "false"
            else:
                sys.exit(f"[错误] 参数 {name} 的 bool 默认值只能为 true/false/1/0，收到 {default!r}")
        params.append((name, ptype, default, default_raw))
    return params


def param_cap(name: str) -> str:
    """maxIter -> MaxIter"""
    return name[0].upper() + name[1:]


def param_member(name: str) -> str:
    """maxIter -> m_MaxIter（遵循仓库 m_ + 驼峰惯例）"""
    return "m_" + param_cap(name)


def cpp_type_of(ptype: str) -> str:
    """参数类型 -> C++ 类型名（成员/返回类型）"""
    return {"string": "std::string"}.get(ptype, ptype)


def setter_param_type(ptype: str) -> str:
    """参数类型 -> Setter 形参类型（string 按 const 引用传入）"""
    return "const std::string&" if ptype == "string" else ptype


def type_info(kind: str) -> tuple[str, str, bool]:
    return TYPE_MAP[kind]


def build_header(args: argparse.Namespace, params: list[tuple[str, str, str, str]]) -> str:
    cls = args.name
    in_cls, in_hdr, _ = type_info(args.input_type)
    out_cls, out_hdr, _ = type_info(args.output_type)
    has_string = any(p[1] == "string" for p in params)

    lines = [
        "// ============================================================================",
        f"// {cls}  — iGameVis Filter 骨架（由 Script/igame_new_filter.py 自动生成）",
        f"// 生成时间: {datetime.date.today().isoformat()}",
        f"// 数据流: {args.input_type} -> {args.output_type}   输入端口 {args.inputs} / 输出端口 {args.outputs}",
        "// 使用方式: 打开 iGame" + cls + ".cpp，在 Execute() 的 ALGORITHM REPLACEMENT AREA",
        "//           中填写你的算法即可（可加成员函数，可加私有辅助方法）。",
        "// ============================================================================",
        "#pragma once",
        "",
        "#include <iGameFilter.h>",
        f"#include <{in_hdr}>",
        (f"#include <{out_hdr}>" if out_hdr != in_hdr else ""),
        ("#include <string>" if has_string else ""),
        "",
        "IGAME_NAMESPACE_BEGIN",
        "",
        f"class {cls} : public Filter {{",
        "public:",
        f"    I_OBJECT({cls});",
        f"    static Pointer New() {{ return new {cls}; }}",
        "",
        "    bool Execute() override;",
        "",
    ]
    if params:
        lines.append("    // ---- 算法参数（由脚本生成，按需增删）----")
        for name, ptype, default, _ in params:
            cap = param_cap(name)
            mem = param_member(name)
            lines.append(f"    void Set{cap}({setter_param_type(ptype)} value) {{ {mem} = value; }}")
            lines.append(f"    {cpp_type_of(ptype)} Get{cap}() const {{ return {mem}; }}")
        lines.append("")
    lines += [
        "protected:",
        f"    {cls}();",
        "    ~" + cls + "() override = default;",
        "",
        "private:",
    ]
    if params:
        lines.append("    // ---- 参数成员（由脚本生成）----")
        for name, ptype, default, _ in params:
            if ptype == "string":
                escaped = default.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f"    std::string {param_member(name)} = \"{escaped}\";")
            else:
                lines.append(f"    {cpp_type_of(ptype)} {param_member(name)} = {default};")
    else:
        lines.append("    // （当前没有参数；算法需要什么就在这里加什么）")
    lines += [
        "};",
        "",
        "IGAME_NAMESPACE_END",
        "",
    ]
    return "\n".join(line for line in lines if line != "") + "\n"


def build_cpp(args: argparse.Namespace, params: list[tuple[str, str, str, str]]) -> str:
    cls = args.name
    in_cls, _, in_cast = type_info(args.input_type)
    out_cls, _, _ = type_info(args.output_type)

    lines = [
        "// ============================================================================",
        f"// {cls}  — iGameVis Filter 骨架（由 Script/igame_new_filter.py 自动生成）",
        f"// 生成时间: {datetime.date.today().isoformat()}",
        "// 固定部分不要改；只填写 ALGORITHM REPLACEMENT AREA。",
        "// ============================================================================",
        f'#include "iGame{cls}.h"',
        "",
        "IGAME_NAMESPACE_BEGIN",
        "",
        f"{cls}::{cls}() {{",
        f"    SetNumberOfInputs({args.inputs});",
        f"    SetNumberOfOutputs({args.outputs});",
        "}",
        "",
        f"bool {cls}::Execute() {{",
        "    // ================= 固定部分：取输入并校验 =================",
    ]
    if in_cast:
        lines += [
            f"    auto in = DynamicCast<{in_cls}>(GetInput(0));",
            "    if (in.IsNull()) return false;",
        ]
    else:
        lines += [
            "    auto in = GetInput(0);",
            "    if (in.IsNull()) return false;",
        ]
    lines += [
        "",
        "    // ================= 固定部分：准备输出对象 =================",
    ]
    if args.mode == "copy" and args.input_type == args.output_type:
        lines += [
            f"    auto out = {out_cls}::New();",
            "    out->DeepCopy(in);   // 拓扑不变、只改坐标；若算法改变拓扑请改为自行构造输出",
        ]
    else:
        if args.input_type != args.output_type:
            lines.append("    // [提示] 输入输出类型不同，不能直接 DeepCopy，请自行构造输出。")
        lines.append(f"    auto out = {out_cls}::New();")
    lines += [
        "",
        "    // ================= ALGORITHM REPLACEMENT AREA =================",
        "    // TODO: 在这里填写你的算法",
        "    //",
        "    // 读取输入:  in->GetPoint(i); in->GetCellArray(); in->GetCellPointIds(cellId, ids); ...",
        "    // 写输出:    out->SetPoint(i, newPos); out->AddPoint(p); ...",
        "    // 进度反馈:  UpdateProgress(0.0 ~ 1.0);   // 可选，界面进度条自动联动",
        "    // 失败返回:  return false;",
        "    //",
    ]
    for name, ptype, default, _ in params:
        lines.append(f"    // 参数: {param_member(name)}（默认 {default}）")
    lines += [
        "    // ===============================================================",
        "",
        "    // ================= 固定部分：通知变更并挂载输出 =================",
        "    out->Modified();",
        "    SetOutput(0, out);",
        "    return true;",
        "}",
        "",
        "IGAME_NAMESPACE_END",
        "",
    ]
    return "\n".join(lines) + "\n"


def print_qt_snippet(args: argparse.Namespace, params: list[tuple[str, str, str, str]]) -> None:
    cls = args.name
    title = args.title if args.title else cls
    print("\n" + "=" * 80)
    print("Qt 菜单接线示例（加入 igQtMainWindow::initAllFilters() 的 ui->menu_filters 区块）")
    print("=" * 80)
    print(f'''    QMenu* hwMenu = ui->menu_filters->addMenu(QStringLiteral("{title}"));
    connect(hwMenu->addAction(QStringLiteral("{title}")), &QAction::triggered, this, [&](bool) {{
        auto obj = rendererWidget->GetScene()->GetCurrentModel()
                       ? rendererWidget->GetScene()->GetCurrentModel()->GetDataObject()
                       : nullptr;
        if (!obj) {{ showDarkFramelessMessage("提示", "请先导入并选择模型"); return; }}

        auto* dlg = new igQtFilterDialogDockWidget(this, true);
        dlg->setFilterTitle(QStringLiteral("{title}"));
''')
    for name, ptype, _default_cpp, default_raw in params:
        qlabel = name
        if ptype == "bool":
            print(f'''        int {name}Id = dlg->addParameter(igQtFilterDialogDockWidget::QT_CHECK_BOX, QStringLiteral("{qlabel}"), "{default_raw}");''')
        else:
            print(f'''        int {name}Id = dlg->addParameter(igQtFilterDialogDockWidget::QT_LINE_EDIT, QStringLiteral("{qlabel}"), "{default_raw}");''')
    print(f'''        dlg->show();
        dlg->setApplyFunctor([=, this]() {{
            bool ok;
            {cls}::Pointer f = {cls}::New();
            f->SetInput(obj);
''')
    for name, ptype, _default_cpp, _default_raw in params:
        if ptype == "int":
            expr = f"dlg->getInt({name}Id, ok)"
        elif ptype == "float":
            expr = f"static_cast<float>(dlg->getDouble({name}Id, ok))"
        elif ptype == "double":
            expr = f"dlg->getDouble({name}Id, ok)"
        elif ptype == "bool":
            expr = f"dlg->getChecked({name}Id, ok)"
        else:
            print(f"            // [注意] string 参数 {name} 无现成 getter：")
            print(f'            //   用 auto* le = dlg->findChild<QLineEdit*>(QStringLiteral("param_{name}"));')
            expr = 'QStringLiteral("") /* TODO: 自行读取 string 参数 */'
        print(f"            f->Set{name[0].upper()}{name[1:]}({expr});")
    print(f'''            if (!f->Execute()) {{ dlg->close(); return; }}
            modelTreeWidget->addDataObjectToModelTree(f->GetOutput(0), Algorithm);
            rendererWidget->update();
            dlg->close();
        }});
    }});''')
    print("=" * 80)


def project_filters_root() -> Path:
    """本脚本所属项目的 Filters 根目录（iGameCore/Filters）。"""
    return (Path(__file__).resolve().parent.parent / "iGameCore" / "Filters").resolve()


def validate_out_dir(out_dir: Path, filters_root: Path) -> str | None:
    """校验输出目录：必须已存在且位于项目 Filters 内。返回错误信息，合法时返回 None。"""
    if not out_dir.is_dir():
        return f"输出目录不存在: {out_dir}"
    try:
        out_dir.relative_to(filters_root)
    except ValueError:
        return f"输出目录必须在项目 Filters 目录内: {filters_root}"
    return None


def find_filter_includes(out_dir: Path, filters_root: Path) -> Path | None:
    """在项目 Filters 目录内向上查找 iGameFilterIncludes.h；找不到返回 None。"""
    cur = out_dir
    while True:
        candidate = cur / "iGameFilterIncludes.h"
        if candidate.is_file():
            return candidate
        if cur == filters_root:
            return None
        cur = cur.parent


def add_include_to_includes(includes_h: Path, h_path: Path) -> bool:
    """把生成的头文件追加到 iGameFilterIncludes.h；返回是否添加成功。"""
    try:
        rel = h_path.relative_to(includes_h.parent).as_posix()
        line = f'#include "{rel}"'
        text = includes_h.read_text(encoding="utf-8")
        if rel in text:
            print(f"[跳过] {includes_h} 已包含 {rel}（无需重复添加）")
            return True
        includes_h.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf-8", newline="\n")
        print(f"[OK] 已追加到 {includes_h}: {line}")
        return True
    except (OSError, ValueError) as e:
        print(f"[错误] 追加 include 失败: {e}")
        return False


def main() -> int:
    args = parse_args()
    args.name = sanitize_identifier(args.name)
    params = parse_params(args.param)

    filters_root = project_filters_root()
    out_dir = Path(args.dir).resolve() if args.dir else filters_root

    # 先做全部路径校验；任何一项不满足就报错返回，不生成也不追加任何文件
    err = validate_out_dir(out_dir, filters_root)
    if err:
        print(f"[错误] {err}")
        return 1

    includes_h = None
    if args.update_includes:
        includes_h = find_filter_includes(out_dir, filters_root)
        if includes_h is None:
            print(f"[错误] 未找到 iGameFilterIncludes.h（应位于 {filters_root} 下），已中止，未生成任何文件。"
                  "可用 --no-update-includes 跳过该步骤。")
            return 1

    file_stem = f"iGame{args.name}"
    h_path = out_dir / f"{file_stem}.h"
    cpp_path = out_dir / f"{file_stem}.cpp"
    for p in (h_path, cpp_path):
        if p.exists() and not args.force:
            print(f"[错误] 文件已存在: {p}（如需覆盖请加 --force）")
            return 1

    try:
        h_path.write_text(build_header(args, params), encoding="utf-8", newline="\n")
        cpp_path.write_text(build_cpp(args, params), encoding="utf-8", newline="\n")
    except OSError as e:
        print(f"[错误] 写入生成文件失败: {e}")
        return 1

    print(f"[OK] 已生成:")
    print(f"     {h_path}")
    print(f"     {cpp_path}")
    print("     下一步：打开 .cpp，在 ALGORITHM REPLACEMENT AREA 中填写算法，然后编译。")

    if args.update_includes and includes_h is not None:
        if not add_include_to_includes(includes_h, h_path):
            return 1

    if args.qt:
        print_qt_snippet(args, params)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
