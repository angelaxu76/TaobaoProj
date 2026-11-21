"""
刷新黑名单商品在供应商端当前是否打折（写回 cur_* / released_at 字段）。
发布 Excel 生成时 load_publish_blocklist() 也会自动刷新，这里用于单独查看。
"""
from common.publication.publish_blocklist import refresh_discount_status

# True = 只检查「打折后可发布」的商品；False = 检查全部启用中的商品
ONLY_RELEASE_ON_DISCOUNT = True

if __name__ == "__main__":
    res = refresh_discount_status(only_release_on_discount=ONLY_RELEASE_ON_DISCOUNT)
    if res.empty:
        print("ℹ️ 没有需要检查的商品")
    else:
        hit = res[res["cur_is_discounted"] == True]  # noqa: E712
        if not hit.empty:
            print("\n当前打折（将被放行）：")
            print(hit[["code_key", "brand", "cur_original_price_gbp", "cur_discount_price_gbp"]].to_string(index=False))
