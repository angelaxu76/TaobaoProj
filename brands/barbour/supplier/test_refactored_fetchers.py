# -*- coding: utf-8 -*-
"""
测试重构后的采集器 - 基本功能验证

验证内容:
1. 类继承关系
2. 必需方法存在
3. 配置正确性
4. 输出字段完整性

使用方式:
    python -m brands.barbour.supplier.test_refactored_fetchers
"""

from __future__ import annotations

import sys
from pathlib import Path


def test_imports():
    """Test imports"""
    print("=" * 60)
    print("Test 1: Import Test")
    print("=" * 60)

    errors = []

    try:
        from brands.barbour.supplier.outdoorandcountry_fetch_info_v3 import OutdoorAndCountryFetcher
        print("[PASS] outdoorandcountry_fetch_info_v3.py")
    except Exception as e:
        print(f"[FAIL] outdoorandcountry_fetch_info_v3.py: {e}")
        errors.append(("outdoorandcountry_fetch_info_v3", e))

    try:
        from brands.barbour.supplier.terraces_fetch_info_v2 import TerracesFetcher
        print("[PASS] terraces_fetch_info_v2.py")
    except Exception as e:
        print(f"[FAIL] terraces_fetch_info_v2.py: {e}")
        errors.append(("terraces_fetch_info_v2", e))

    try:
        from brands.barbour.supplier.philipmorrisdirect_fetch_info_v3 import PhilipMorrisFetcher
        print("[PASS] philipmorrisdirect_fetch_info_v3.py")
    except Exception as e:
        print(f"[FAIL] philipmorrisdirect_fetch_info_v3.py: {e}")
        errors.append(("philipmorrisdirect_fetch_info_v3", e))

    try:
        from brands.barbour.supplier.houseoffraser_fetch_info_v4 import HouseOfFraserFetcher
        print("[PASS] houseoffraser_fetch_info_v4.py")
    except Exception as e:
        print(f"[FAIL] houseoffraser_fetch_info_v4.py: {e}")
        errors.append(("houseoffraser_fetch_info_v4", e))

    print()
    return errors


def test_inheritance():
    """Test inheritance"""
    print("=" * 60)
    print("Test 2: Inheritance Test")
    print("=" * 60)

    from brands.barbour.core.base_fetcher import BaseFetcher
    from brands.barbour.supplier.outdoorandcountry_fetch_info_v3 import OutdoorAndCountryFetcher
    from brands.barbour.supplier.terraces_fetch_info_v2 import TerracesFetcher
    from brands.barbour.supplier.philipmorrisdirect_fetch_info_v3 import PhilipMorrisFetcher
    from brands.barbour.supplier.houseoffraser_fetch_info_v4 import HouseOfFraserFetcher

    classes = [
        ("OutdoorAndCountryFetcher", OutdoorAndCountryFetcher),
        ("TerracesFetcher", TerracesFetcher),
        ("PhilipMorrisFetcher", PhilipMorrisFetcher),
        ("HouseOfFraserFetcher", HouseOfFraserFetcher),
    ]

    errors = []

    for name, cls in classes:
        if issubclass(cls, BaseFetcher):
            print(f"[PASS] {name} inherits BaseFetcher")
        else:
            print(f"[FAIL] {name} does not inherit BaseFetcher")
            errors.append((name, "Not a subclass of BaseFetcher"))

    print()
    return errors


def test_required_methods():
    """测试必需方法"""
    print("=" * 60)
    print("测试 3: 必需方法测试")
    print("=" * 60)

    from brands.barbour.supplier.outdoorandcountry_fetch_info_v3 import OutdoorAndCountryFetcher
    from brands.barbour.supplier.terraces_fetch_info_v2 import TerracesFetcher
    from brands.barbour.supplier.philipmorrisdirect_fetch_info_v3 import PhilipMorrisFetcher
    from brands.barbour.supplier.houseoffraser_fetch_info_v4 import HouseOfFraserFetcher

    classes = [
        ("OutdoorAndCountryFetcher", OutdoorAndCountryFetcher),
        ("TerracesFetcher", TerracesFetcher),
        ("PhilipMorrisFetcher", PhilipMorrisFetcher),
        ("HouseOfFraserFetcher", HouseOfFraserFetcher),
    ]

    required_methods = [
        "parse_detail_page",  # 抽象方法 (或 fetch_one_product)
        "run_batch",          # 批量入口
        "fetch_one_product",  # 单个商品抓取
    ]

    errors = []

    for name, cls in classes:
        print(f"\n{name}:")
        for method_name in required_methods:
            if hasattr(cls, method_name):
                print(f"  [PASS] {method_name}")
            else:
                print(f"  [FAIL] {method_name} missing")
                errors.append((name, f"Missing method: {method_name}"))

    print()
    return errors


def test_configuration():
    """测试配置"""
    print("=" * 60)
    print("测试 4: 配置测试")
    print("=" * 60)

    from config import BARBOUR

    sites = ["outdoorandcountry", "terraces", "philipmorris", "houseoffraser"]
    errors = []

    for site in sites:
        print(f"\n{site}:")

        # 检查链接文件
        if site in BARBOUR["LINKS_FILES"]:
            links_file = BARBOUR["LINKS_FILES"][site]
            if Path(links_file).exists():
                print(f"  [PASS] LINKS_FILES['{site}'] exists: {links_file}")
            else:
                print(f"  [WARN] LINKS_FILES['{site}'] does not exist: {links_file}")
        else:
            print(f"  [FAIL] LINKS_FILES['{site}'] not configured")
            errors.append((site, "LINKS_FILES not configured"))

        # 检查输出目录
        if site in BARBOUR["TXT_DIRS"]:
            txt_dir = BARBOUR["TXT_DIRS"][site]
            print(f"  [PASS] TXT_DIRS['{site}'] configured: {txt_dir}")
        else:
            print(f"  [FAIL] TXT_DIRS['{site}'] not configured")
            errors.append((site, "TXT_DIRS not configured"))

    print()
    return errors


def test_output_fields():
    """测试输出字段"""
    print("=" * 60)
    print("测试 5: 输出字段测试 (Mock)")
    print("=" * 60)

    # 必需字段
    required_fields = [
        "Product Code",
        "Product Name",
        "Product Color",
        "Product Gender",
        "Product Description",
        "Original Price (GBP)",
        "Discount Price (GBP)",
        "Product Size",
        "Product Size Detail",
    ]

    # 自动添加字段
    auto_fields = [
        "Site Name",
        "Source URL",
    ]

    print("必需字段 (parse_detail_page 返回):")
    for field in required_fields:
        print(f"  - {field}")

    print("\n自动添加字段 (BaseFetcher 添加):")
    for field in auto_fields:
        print(f"  - {field}")

    print("\n[INFO] 实际输出字段需要在真实抓取后验证")
    print()
    return []


def test_main_functions():
    """测试主函数"""
    print("=" * 60)
    print("测试 6: 主函数存在性测试")
    print("=" * 60)

    errors = []

    try:
        from brands.barbour.supplier.outdoorandcountry_fetch_info_v3 import outdoorandcountry_fetch_info
        print("[PASS] outdoorandcountry_fetch_info()")
    except Exception as e:
        print(f"[FAIL] outdoorandcountry_fetch_info(): {e}")
        errors.append(("outdoorandcountry_fetch_info", e))

    try:
        from brands.barbour.supplier.terraces_fetch_info_v2 import terraces_fetch_info
        print("[PASS] terraces_fetch_info()")
    except Exception as e:
        print(f"[FAIL] terraces_fetch_info(): {e}")
        errors.append(("terraces_fetch_info", e))

    try:
        from brands.barbour.supplier.philipmorrisdirect_fetch_info_v3 import philipmorris_fetch_info
        print("[PASS] philipmorris_fetch_info()")
    except Exception as e:
        print(f"[FAIL] philipmorris_fetch_info(): {e}")
        errors.append(("philipmorris_fetch_info", e))

    try:
        from brands.barbour.supplier.houseoffraser_fetch_info_v4 import houseoffraser_fetch_info
        print("[PASS] houseoffraser_fetch_info()")
    except Exception as e:
        print(f"[FAIL] houseoffraser_fetch_info(): {e}")
        errors.append(("houseoffraser_fetch_info", e))

    print()
    return errors


def main():
    """主测试流程"""
    print("\n")
    print("#" * 60)
    print("# Barbour 采集器重构 - 功能验证测试")
    print("#" * 60)
    print()

    all_errors = []

    # 测试 1: 导入
    all_errors.extend(test_imports())

    # 测试 2: 继承
    all_errors.extend(test_inheritance())

    # 测试 3: 方法
    all_errors.extend(test_required_methods())

    # 测试 4: 配置
    all_errors.extend(test_configuration())

    # 测试 5: 输出字段
    all_errors.extend(test_output_fields())

    # 测试 6: 主函数
    all_errors.extend(test_main_functions())

    # 总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)

    if all_errors:
        print(f"\n[FAIL] 发现 {len(all_errors)} 个错误:\n")
        for name, error in all_errors:
            print(f"  - {name}: {error}")
        print()
        return 1
    else:
        print("\n[PASS] 所有测试通过!")
        print("\n建议:")
        print("  1. 准备测试链接文件 (每个站点 1-2 个链接)")
        print("  2. 运行实际抓取测试")
        print("  3. 对比输出 TXT 与旧版一致性")
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
