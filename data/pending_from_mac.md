# งานค้างจากฝั่ง Mac (14 พ.ย. 69 ก่อนปิดเครื่อง)

routine บนคลาวด์ (09:30, 12:00, 21:30) ทำส่วนเทรด หาท่าโม้ ปรับท่า และรายงานต่อเองได้ รายการข้างล่างคือสิ่งที่ routine ทำแทนไม่ได้ หรือยังรอคนตัดสิน

## ต้องใช้ Mac
- backtest ด้วย skill market-timeseries พร้อม DSR/PBO ตาม AGENT_RULES.md: skill อยู่บน Mac เท่านั้น routine ทำได้แค่ backtest ง่ายๆ จาก data/rank_hist ให้รันเมื่อเปิด Mac กับท่าที่มีข้อมูลพอ (i_*, bigliqF, bigliqRC)
- grokbot.py / grokbot.py --team อ่านแชท Grok ใน Chrome Canary: หยุดไปพร้อม Mac และ Grok หมดโควตาจนถึง 19 พ.ย. 69 10:48 ห้ามใช้ Grok ก่อนเช็กโควตาที่ grok.com/?_s=usage
- crypto-regime-analyzer รายวัน และ dashboard 127.0.0.1:8787: หยุดไปพร้อม Mac
- แก้ wallets.py ให้อ่านราคาจาก bonding curve เอง (56 จาก 84 ครั้งที่ข้ามเพราะ DexScreener ให้ liquidity 0)

## รอดูผล
- ท่า i_* ชุดแรก (i_bigliq_cost2, i_bigliq_run24, i_bigliq_mom1h, i_bigdip) และ x_* ระยะสัปดาห์ ตัดสิน 21 พ.ย. 69, x_* ระยะเดือนตัดสิน 14 ธ.ค. 69
- การเทียบราคา DexScreener กับ Jupiter: ดูว่ามีบัญชีขึ้น [halted] บ่อยแค่ไหน และการซื้อถูกปฏิเสธเพราะ price mismatch/unverified กี่ครั้ง ถ้าบ่อยเกินจนบัญชีแทบไม่ได้เทรด ให้รายงานผู้ใช้ (ห้ามแก้เกณฑ์ 1% เอง)
- สถานะบัญชีที่ตายรอบแรก 10 บัญชี (14 พ.ย. 69): savip safe cto kol2 smart10 top1 dip fresh mom5 mom1h

## ต้องให้ผู้ใช้ตัดสิน
- เปิดสิทธิ์เน็ตเต็มให้ environment ของ routine (ตอนนี้เปิดเว็บได้บางโดเมน อ่านโพสต์เต็มไม่ได้ ได้แค่ snippet)
- ไฟล์สำรองบน Mac: Projects/papertrade-cloud-backup-2026-11-14.bundle และ branch backup-before-rewrite ในเครื่อง ลบได้เมื่อผู้ใช้บอก
- เงินจริงยังไม่ใช้ จนกว่าจะมีบัญชีผ่านเกณฑ์ 50 ไม้และผู้ใช้พิมพ์ "กดเลย" ทุกคำสั่ง
