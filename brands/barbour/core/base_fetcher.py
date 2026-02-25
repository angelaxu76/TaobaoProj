# -*- coding: utf-8 -*-
"""
Barbour 采集器基类 - 统一接口和共享逻辑

目标: 消除 8 个采集脚本 70%+ 的代码重复

使用方式:
    class AllweathersFetcher(BaseFetcher):
        def parse_detail_page(self, html, url):
            # 只实现站点特定的解析逻辑
            return {...}

    fetcher = AllweathersFetcher("allweathers", links_file, output_dir)
    fetcher.run_batch()
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

# 导入共享工具模块
from brands.barbour.core.size_normalizer import (
    normalize_size,
    build_size_lines_from_detail,
    format_size_str_simple,
    format_size_detail_simple,
)
from brands.barbour.core.gender_classifier import infer_gender
from brands.barbour.core.html_parser import (
    extract_jsonld,
    extract_meta_tag,
    extract_og_tag,
    extract_price_from_text,
    extract_barbour_code_from_text,
)
from brands.barbour.core.text_utils import (
    clean_text,
    clean_description,
    normalize_url,
    safe_filename,
)

# 导入通用模块
from common.core.selenium_utils import get_driver, quit_driver, quit_all_drivers
from common.ingest.txt_writer import format_txt

# 配置
from config import SETTINGS

DEFAULT_STOCK_COUNT = SETTINGS.get("DEFAULT_STOCK_COUNT", 3)


# ================== 基类定义 ==================

class BaseFetcher(ABC):
    """
    采集器基类 - 模板方法模式

    核心思想:
    - 基类提供通用逻辑 (并发、重试、日志、文件写入)
    - 子类只实现站点特定的解析逻辑 (parse_detail_page)

    特性:
    - 自动并发管理
    - 自动重试 (指数退避)
    - 统一日志
    - 线程安全的驱动管理
    - 统一文件写入格式
    """

    def __init__(
        self,
        site_name: str,
        links_file: Path | str,
        output_dir: Path | str,
        max_workers: int = 4,
        max_retries: int = 3,
        default_stock: int = DEFAULT_STOCK_COUNT,
        wait_seconds: float = 2.0,
        headless: bool = True,
    ):
        """
        初始化采集器

        Args:
            site_name: 站点名称 (如 'allweathers', 'barbour')
            links_file: 链接文件路径
            output_dir: TXT输出目录
            max_workers: 并发线程数
            max_retries: 最大重试次数
            default_stock: 默认库存数量
            wait_seconds: 页面等待时间 (秒)
            headless: 是否使用无头模式
        """
        self.site_name = site_name
        self.links_file = Path(links_file)
        self.output_dir = Path(output_dir)
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.default_stock = default_stock
        self.wait_seconds = wait_seconds
        self.headless = headless

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 日志配置
        self.logger = logging.getLogger(f"{__name__}.{site_name}")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)-8s] [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # 统计
        self._success_count = 0
        self._fail_count = 0
        self._lock = threading.Lock()

    # ================== 抽象方法 - 子类必须实现 ==================

    @abstractmethod
    def parse_detail_page(self, html: str, url: str) -> Dict[str, Any]:
        """
        解析商品详情页 - 各站点实现自己的逻辑

        Args:
            html: 页面HTML源码
            url: 商品URL

        Returns:
            包含以下字段的字典 (必填):
            {
                "Product Code": str,           # Barbour编码
                "Product Name": str,           # 商品名称
                "Product Color": str,          # 颜色
                "Product Gender": str,         # 性别 (Men/Women/Kids)
                "Product Description": str,    # 描述
                "Original Price (GBP)": str,   # 原价
                "Discount Price (GBP)": str,   # 折扣价
                "Product Size": str,           # "S:有货;M:有货;L:无货"
                "Product Size Detail": str,    # "S:3:EAN001;M:0:EAN002"
            }

        注意:
        - 可以使用基类提供的工具方法 (self.extract_*, self.parse_*)
        - 返回的字典会自动添加 Site Name 和 Source URL
        """
        pass

    # ================== 驱动管理 ==================

    def get_driver(self):
        """
        获取 Selenium 驱动 - 线程安全

        Returns:
            WebDriver实例
        """
        return get_driver(
            name=self.site_name,
            headless=self.headless,
            window_size="1920,1080",
        )

    def quit_driver(self):
        """关闭驱动"""
        try:
            quit_driver(self.site_name)
        except Exception as e:
            self.logger.warning(f"驱动关闭失败: {e}")

    # ================== 核心流程 - 模板方法 ==================

    def fetch_one_product(self, url: str, idx: int, total: int) -> Tuple[str, bool]:
        """
        抓取单个商品 - 带重试和错误处理

        Args:
            url: 商品URL
            idx: 当前索引 (从1开始)
            total: 总数

        Returns:
            (url, success: bool)
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"[{idx}/{total}] [{attempt}/{self.max_retries}] 抓取: {url}")

                # Step 1: 获取HTML
                html = self._fetch_html(url)

                # Step 2: 解析
                info = self.parse_detail_page(html, url)

                # Step 3: 验证必填字段
                self._validate_info(info, url)

                # Step 4: 填充默认字段
                info.setdefault("Site Name", self.site_name)
                info.setdefault("Source URL", url)

                # Step 5: 写入文件
                self._write_output(info)

                code = info.get("Product Code", "N/A")
                self.logger.info(f"✅ [{idx}/{total}] 成功: {code}")

                with self._lock:
                    self._success_count += 1

                return url, True

            except Exception as e:
                self.logger.error(
                    f"❌ [{idx}/{total}] 尝试 {attempt}/{self.max_retries} 失败: {url} - {e}",
                    exc_info=(attempt == self.max_retries),  # 最后一次才打印堆栈
                )

                # 指数退避
                if attempt < self.max_retries:
                    wait_time = min(2 ** attempt, 30)  # 最多等30秒
                    time.sleep(wait_time)

                if attempt == self.max_retries:
                    with self._lock:
                        self._fail_count += 1
                    return url, False

        return url, False

    def _fetch_html(self, url: str) -> str:
        """
        获取HTML - 默认实现(Selenium)，子类可覆盖

        复用同线程 driver（由 selenium_utils 按 thread-id 隔离），
        不再每次请求都创建/销毁 Chrome 进程。

        Args:
            url: 商品URL

        Returns:
            HTML源码
        """
        driver = self.get_driver()
        driver.get(url)
        time.sleep(self.wait_seconds)  # 等待渲染
        return driver.page_source

    def _validate_info(self, info: Dict[str, Any], url: str) -> None:
        """
        验证必填字段

        Args:
            info: 商品信息字典
            url: 商品URL

        Raises:
            ValueError: 必填字段缺失
        """
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

        for field in required_fields:
            if field not in info:
                raise ValueError(f"缺失必填字段: {field} (URL: {url})")

    def _write_output(self, info: Dict[str, Any]) -> None:
        """
        写入TXT文件 - 统一格式

        Args:
            info: 商品信息字典
        """
        code = info.get("Product Code", "").strip()
        if not code or code in ["Unknown", "No Data", "N/A", ""]:
            # 使用URL哈希作为文件名
            url = info.get("Source URL", "")
            code = f"NoCode_{abs(hash(url)) & 0xFFFFFFFF:08x}"

        # 清洗文件名
        safe_code = safe_filename(code)
        txt_path = self.output_dir / f"{safe_code}.txt"

        try:
            format_txt(info, txt_path, brand="barbour")
            self.logger.debug(f"写入文件: {txt_path}")
        except Exception as e:
            self.logger.error(f"文件写入失败 {txt_path}: {e}")
            raise

    # ================== 批量入口 ==================

    def run_batch(self) -> Tuple[int, int]:
        """
        批量抓取 - 主入口

        Returns:
            (成功数, 失败数)
        """
        # 读取链接
        if not self.links_file.exists():
            self.logger.error(f"链接文件不存在: {self.links_file}")
            return 0, 0

        urls = self._load_urls()
        if not urls:
            self.logger.warning("无有效链接")
            return 0, 0

        total = len(urls)
        self.logger.info(f"📄 共 {total} 个商品待抓取 (并发度: {self.max_workers})")

        # 并发抓取
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self.fetch_one_product, url, idx + 1, total): url
                    for idx, url in enumerate(urls)
                }

                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        self.logger.error(f"任务异常: {url} - {e}")
        finally:
            quit_all_drivers()
            self.logger.info("🧹 已清理所有 driver")

        # 统计
        success = self._success_count
        fail = self._fail_count
        self.logger.info(f"✅ 完成: 成功 {success}, 失败 {fail}")

        return success, fail

    def _load_urls(self) -> List[str]:
        """
        加载链接列表 - 去重

        Returns:
            URL列表
        """
        try:
            raw_lines = self.links_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as e:
            self.logger.error(f"读取链接文件失败: {e}")
            return []

        seen = set()
        urls = []

        for line in raw_lines:
            url = line.strip()

            # 跳过空行和注释
            if not url or url.startswith("#"):
                continue

            # 标准化URL (去除锚点)
            url = normalize_url(url)

            # 去重
            if url in seen:
                continue

            seen.add(url)
            urls.append(url)

        return urls

    # ================== 工具方法 (供子类使用) ==================

    def extract_jsonld(self, soup: BeautifulSoup, target_type: str = "Product") -> Optional[Dict]:
        """提取 JSON-LD 数据"""
        return extract_jsonld(soup, target_type)

    def extract_meta(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        """提取 meta 标签"""
        return extract_meta_tag(soup, name)

    def extract_og(self, soup: BeautifulSoup, og_type: str) -> Optional[str]:
        """提取 Open Graph 标签"""
        return extract_og_tag(soup, og_type)

    def parse_price(self, text: str) -> Optional[float]:
        """从文本提取价格"""
        return extract_price_from_text(text)

    def clean_text(self, text: str, maxlen: int = 500) -> str:
        """清理文本"""
        return clean_text(text, maxlen=maxlen)

    def clean_description(self, desc: str) -> str:
        """清理描述"""
        return clean_description(desc)

    def infer_gender(
        self,
        text: str = "",
        url: str = "",
        product_code: str = "",
        output_format: str = "en",
    ) -> str:
        """推断性别"""
        return infer_gender(
            text=text,
            url=url,
            product_code=product_code,
            output_format=output_format,
        )

    def normalize_size(self, token: str, gender: str) -> Optional[str]:
        """标准化尺码"""
        return normalize_size(token, gender)

    def build_size_lines(
        self,
        size_detail: Dict[str, Dict],
        gender: str,
    ) -> Tuple[str, str]:
        """从尺码详情生成 Product Size 和 Product Size Detail"""
        return build_size_lines_from_detail(size_detail, gender, self.default_stock)

    def format_size_simple(self, sizes: List[str], gender: str) -> str:
        """简单格式化尺码 (全部有货)"""
        return format_size_str_simple(sizes, gender)

    def format_size_detail_simple(self, sizes: List[str], gender: str) -> str:
        """简单格式化尺码详情"""
        return format_size_detail_simple(sizes, gender, self.default_stock)

    def extract_barbour_code(self, text: str) -> Optional[str]:
        """从文本提取 Barbour Product Code"""
        return extract_barbour_code_from_text(text)


# ================== 辅助函数 ==================

def setup_logging(level: int = logging.INFO):
    """
    配置全局日志

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
