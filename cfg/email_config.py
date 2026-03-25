# cfg/email_config.py
# 邮件账号配置（SMTP）

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# 发件账号
EMAIL_SENDER = "xunianzhou7@gmail.com"
EMAIL_PASSWORD = "ddggppssztgrdjtp"  # Gmail App Password（不是登录密码），在 Google 账户 -> 安全 -> 应用专用密码 生成

# 收件人列表
ECMS_RECIPIENTS = [
    "Zhen.zhao@ecmsglobal.com",
    "Cainiao_EU_Inbound_Notification_Receiver@list.alibaba-inc.com",
    "cs.uk@ecmsglobal.com",
    "cainiaouk@ecmsglobal.com",
    "ops.uk@ecmsglobal.com",
]

# ECMS_RECIPIENTS = [
#     "angela112617@gmail.com"
# ]