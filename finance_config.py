from pathlib import Path

FINANCE_EES = {
    "exporter": {
        "name": "EMINZORA TRADE LTD",
        "address": "3rd Floor,86-90 PAUL STREET, LONDON, United Kingdom, EC2A 4NE",
        "company_no": "16249886",
        "vat_no": "GB487486722",
        "eori_no": "GB487486722000",
        "phone": "+44 7305996590",
        "email": "xunianzhou3@gmail.com",
    },
    "consignee": {
        "name": "HONG KONG ANGEL XUAN TRADING CO., LIMITED",
        "address": "FLAT/RM D07, 8/F, Kai Tak Fty Building, No. 99 King Fuk Street, Sanpokong, Kowloon, Hong Kong",
        "phone": "+8617741796346",
        "email": "maxiaodan2015@gmail.com",
    },
    "logistics": {
        "carrier": "ECMS",
        "route": "UK → China",
    },

    "bank": {
        "bank_name": "ANNA Money",                       # 银行名称（如 Barclays, HSBC）
        "account_name": "EMINZORA TRADE LTD",  # 账户名称（一般等于公司名）
        "account_no": "86092219",                      # 银行账号
        "sort_code": "23-11-85",                       # Sort Code（xx-xx-xx）
        "iban": "GB26PAYR23118586092219",                            # IBAN（如 GBxx...）
        "swift": "",                           # SWIFT/BIC（如 BUKBGB22）
    },    

    # "bank": {
    #     "bank_name": "Wise Payments Limited",                       # 银行名称（如 Barclays, HSBC）
    #     "account_name": "EMINZORA TRADE LTD",  # 账户名称（一般等于公司名）
    #     "account_no": "39155857",                      # 银行账号
    #     "sort_code": "60-84-64",                       # Sort Code（xx-xx-xx）
    #     "iban": "GB54 TRWI 6084 6439 1558 57",                            # IBAN（如 GBxx...）
    #     "swift": "TRWIGB2LXXX",                           # SWIFT/BIC（如 BUKBGB22）
    # },    
    "declaration": (
        "I confirm that the goods listed above were exported from the United Kingdom "
        "within three months of their purchase or acquisition, and that the full set "
        "of supporting documents (including supplier invoices, packing lists, and "
        "freight documents) is retained for the statutory period, in accordance with "
        "HMRC Notice 703, qualifying this supply for zero-rated VAT treatment."
    ),
    "signature": {
        "image_path": Path(
            r"D:\OneDrive\CrossBorderDocs_UK\00_Templates\signatures\xiaodan_ma_signature.png"
        ),
        "sign_name": "XIAODAN MA",
        "sign_title": "Director, EMINZORA TRADE LTD",
    },
}
