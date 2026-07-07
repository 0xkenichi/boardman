from gaming.src.backend.psn_layer import PSNLayer

psn = PSNLayer()
try:
    res = psn.verify_sybill("0xKenichi-Sama")
    print(res)
except Exception as e:
    print("Error:", e)
