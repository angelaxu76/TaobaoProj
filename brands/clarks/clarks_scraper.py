import requests
from bs4 import BeautifulSoup
import os
from pathlib import Path
from common.scraper_base import ProductScraper

class ClarksScraper(ProductScraper):
    def fetch_product_info(self, url: str) -> dict:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        result = {
            "Product Code": url.split("/")[-1].split("-")[0],
            "Product Name": soup.title.get_text(strip=True),
            "Product Description": "",
            "Product Gender": "women" if "/women" in url.lower() else "men",
            "Color": "No Data",
            "Original Price": "No Data",
            "Actual Price": "No Data",
            "Product URL": url,
            "Upper Material": "No Data",
            "Lining Material": "No Data",
            "Sole Material": "No Data",
            "Midsole Material": "No Data",
            "Fastening Type": "No Data",
            "Trims": "No Data",
            "Sock Material": "No Data",
            "Size Stock (EU)": ""
        }

        # 提取描述
        desc = soup.find("div", class_="product-description")
        if desc:
            result["Product Description"] = desc.get_text(strip=True)

        # 提取价格
        price_block = soup.select_one("div.price.price--large")
        if price_block:
            price = price_block.get_text(strip=True).replace("£", "")
            result["Actual Price"] = f"£{price}"

        # 提取材质信息（如果有）
        for li in soup.select("ul.accordion__content li"):
            text = li.get_text(strip=True)
            if "Upper Material" in text:
                result["Upper Material"] = text.split(":")[-1].strip()
            elif "Lining Material" in text:
                result["Lining Material"] = text.split(":")[-1].strip()
            elif "Sole Material" in text:
                result["Sole Material"] = text.split(":")[-1].strip()
            elif "Midsole Material" in text:
                result["Midsole Material"] = text.split(":")[-1].strip()
            elif "Fastening Type" in text:
                result["Fastening Type"] = text.split(":")[-1].strip()
            elif "Sock Material" in text:
                result["Sock Material"] = text.split(":")[-1].strip()
            elif "Trims" in text:
                result["Trims"] = text.split(":")[-1].strip()

        # 提取尺码信息（示例，仅保留结构）
        sizes = []
        for size_div in soup.select("label.size-tile__label"):
            size_text = size_div.get_text(strip=True)
            if "EU" in size_text:
                eu_size = size_text.replace("EU", "").strip()
                if "Out of stock" in size_div.text:
                    sizes.append(f"{eu_size}:无货")
                else:
                    sizes.append(f"{eu_size}:有货")
        result["Size Stock (EU)"] = ";".join(sizes)

        return result

    def fetch_product_images(self, url: str, output_dir: str) -> None:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tags = soup.select("li.thumbnail img")

        product_code = url.split("/")[-1].split("-")[0]
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for idx, tag in enumerate(img_tags, start=1):
            img_url = tag.get("src") or tag.get("data-src")
            if img_url and not img_url.startswith("http"):
                img_url = "https:" + img_url
            try:
                img_data = requests.get(img_url, timeout=10).content
                img_file = output_path / f"{product_code}_{idx}.jpg"
                with open(img_file, "wb") as f:
                    f.write(img_data)
            except Exception as e:
                print(f"❌ 图片下载失败: {img_url} - {e}")