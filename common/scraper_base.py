from abc import ABC, abstractmethod

class ProductScraper(ABC):
    @abstractmethod
    def fetch_product_info(self, url: str) -> dict:
        """
        抓取商品页面并返回标准字段的字典
        """
        pass

    @abstractmethod
    def fetch_product_images(self, url: str, output_dir: str) -> None:
        """
        下载商品图片并保存至 output_dir
        """
        pass