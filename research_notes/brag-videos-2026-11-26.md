# ตรวจคลิปโพสต์อวดบอทเทรด 27 คลิป (26 พ.ย. 69)

ดู contact sheet 2 เฟรมต่อวินาทีทุกคลิป (โพสต์ใน x_recipes.json 14 คลิป + โพสต์ที่ผู้ใช้กดใจ 13 คลิป) ไฟล์ดิบอยู่ scratchpad/brag (ชั่วคราว)

ผลรวม
- คลิป "Grok Bot ข้ามคืน" ทุกคลิป (ราว 20 คลิป) เป็นภาพเคลื่อนไหวที่ทำขึ้น ไม่ใช่การอัดจอ ตัวเลขขัดกันเองทุกคลิป ไม่มีที่อยู่กระเป๋า สัญญา หรือธุรกรรมเต็มเลย
- บอกเองว่าไม่ใช่เงินจริง: 0xLotttus ("illustrative replay"), Loofyb0i (SIM), crbpite8 2121445946 (paper/SIM), w1nklerr ("demo · simulated · not real trades"), Corki_0x (paper), rikittan (paper-test)
- เลข slot Solana ราว 318 ล้านในหลายคลิป (Maleomx, Hrundel75, Brankotrcek) เป็นของต้นปี 2025 ไม่ใช่ พ.ย. 2026
- ปลายทางคือ funnel: referral GMGN (gmgn.ai/r/MjhhuWaq), fomo.family/r/qkl2058, "comment GRAD", บทความใน X, ปุ่ม "trade with Grok Bot"
- บัญชีโยงกัน: Maleomx quote A_Pirate_I quote morpphhhaw, whoyatagarasu quote x_insider4, หลายคลิปดัน "Jev"

ข้อมูลจริงแต่โพสต์บิด
- whoyatagarasu: trader Jols ถือ PONS (Robinhood Chain) ใส่ $134.6K ออกได้ $555K ($1.32M คือมูลค่าตอนพีกที่ไม่ได้ขาย)
- goddyfx01: MT5 จริง (XAUUSDm แบบ Exness) แต่ 51 นาทีไม่ใช่ 2 นาที ไม่มีบอท เลเวอเรจเต็มพอร์ตกับทอง เกือบแตกหลายรอบ
- Polymarket blue.birds (0xb9587c373c773d023f47c2f85a30b3d5bddcf513): ประวัติจริง 20,000 ไม้ล่าสุด เป็น market maker ซื้อทั้ง Up และ Down ใน 90% ของตลาด BTC/ETH 5 นาที รวมสองฝั่งเฉลี่ย 0.98 ราว 43% เป็น maker fill มัธยฐานไม้ละ $9 ไม่ใช่ "ซื้อ 20-35 เซนต์" ตามโพสต์ Mikocrypto11
- Jane Street (carm1nee): repo จริง (EnriqueKhai/JaneStreetETC22, yafet-a/Jane-Street-FTTP-Trading-Bot) แต่ "MIT", "$3,394,715" ไม่อยู่ใน README ได้ผลเฉพาะในตลาดจำลองที่ fair value ตายตัว (BOND=1000, VALE=VALBZ) คลิปเอาไปลอง BTC เองได้ +$12.63 และ -$4.74 ก่อนค่าธรรมเนียม
- _zheergen: รีวิวเครื่องมือ (qlib, RD-Agent, vectorbt, nautilus, LEAN, FinRL) ซื่อสัตย์ กราฟ SMA ที่ดีที่สุดเป็น in-sample

กฎที่พอทดสอบได้ (เชื่อแค่กฎ ไม่เชื่อตัวเลข)
1. tigra_ai: เหรียญ graduate, dev <=10%, funder cluster <=25%, holder โต 1.15 เท่าใน 10 นาที, รอย่อ 18% จาก high 90 วิ ภายใน 15 นาที, stop -12%, กำไรเกิน 40% trail 15%
2. Hrundel75 CTO หลัง rug: dev ขาย >=90% เหลือ 0%, holder +15% หลังทุบ, มี CTO บน DexScreener, ขายครึ่งที่ mcap เท่าตอน dev ขาย, trail 15%, stop -18%
3. crbpite8 ก๊อปเทรด: leader อันดับต้น 7/30 วันบน fomo, liq >= $35-40K, ไม่ไล่ราคา, 20% ต่อไม้ สูงสุด 2 ไม้, stop -8%, trail 20/15, ขายตามเมื่อ leader ขาย
4. กลุ่ม pump.fun ทั่วไป: liq < $20-25K ข้าม, stop -25%, 2 เท่าขายครึ่ง, trail ที่เหลือ

## Backtest กฎจากคลิป (26 พ.ย. 69 03:55)
ข้อมูล: เหรียญ pump.fun ที่ย้ายตลาด (graduated) ใน 14 ชม. ล่าสุด 407 เหรียญ มีแท่งนาทีจาก GeckoTerminal 375 เหรียญ ค่าธรรมเนียม+slippage 2% ต่อขา ตัวควบคุมคือเข้าแบบสุ่มนาทีที่ 2-15 ด้วยทางออกเดียวกัน (20 รอบสุ่ม)
- tigra_ai (เข้าเมื่อย่อ 18% จาก high 2 นาทีแรก, stop -12%, กำไร 40% แล้ว trail 15%): n 336 เฉลี่ย +10.2% มัธยฐาน -15.5% ชนะ 23% แต่ตัดเหรียญดีสุดเหรียญเดียว (+4,718%) ออกแล้ว -3.9% ตัวสุ่ม -0.5% ตัด 5 ตัวดีสุด กฎ -9.5% สุ่ม -5.1% แพ้ตัวสุ่มทุกระดับ 90% ของเหรียญย่อถึงจุดเข้าอยู่แล้ว กฎจึงแทบเท่ากับ "ซื้อทุกเหรียญ" ตาย
- กฎทั่วไป (stop -25%, ถึง 2 เท่าแล้ว trail 30%): n 336 เฉลี่ย +9.2% มัธยฐาน -28% ตัดตัวดีสุดแล้ว -2.3% ไม่ต่างจากสุ่ม ตาย
- ข้อจำกัด: ใช้ราคา stop ตรงๆ (ของจริงหลุดแย่กว่า) และข้อมูลแค่ 14 ชม. แต่ผลเอียงไปทางดีอยู่แล้วยังไม่ผ่าน
- crbpite8 (ก๊อปเทรด) และ Hrundel75 (CTO) ต้องใช้ข้อมูลกระเป๋า/ธุรกรรมราย wallet ยังไม่ได้ทดสอบ
