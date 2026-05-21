"""scripts/seed.py — Seed banner registry."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db.session import init_db, AsyncSessionLocal
from backend.db.models import Banner
from sqlalchemy import select

BANNERS = [
    {"url_id":"1","name":"Gilead · Delay Time Banner (Repatha 160x600)",
     "url":"https://doc-00-3s-adspreview.googleusercontent.com/preview/9o5bees06oeguhr10neq55qcti27eh7n/8sij95kcp2anq3r168eri4mv0mam4mqk/1778155200000/62942889/previewuser/ads-richmedia-studio.62942889?render=blank&appName=Repatha_USA-CCF-84264_ASC-58052_Banner_160x600&appHeight=600&appWidth=160","client":"Gilead","dimensions":"160x600"},
    {"url_id":"2","name":"Gilead · LMS Link Content Overlapping Demo",
     "url":"https://lms-us.indegene.com/Gilead/Banner/Nikhil/LMS_Link_Content_Overlapping/demo_1/demo/index.html","client":"Gilead","dimensions":None},
    {"url_id":"3","name":"Bayer CS · Nubeqa Safety 300x250",
     "url":"https://lms-us.indegene.com/Bayer_CS/test/nubeqa_safety/300x250/index.html","client":"Bayer CS","dimensions":"300x250"},
    {"url_id":"4","name":"Gilead · Delay Time Banner",
     "url":"https://lms-us.indegene.com/Gilead/Banner/Nikhil/DelayTime/delay_time/index.html","client":"Gilead","dimensions":None},
    {"url_id":"5","name":"Gilead GFC-15565 · 300x250",
     "url":"https://lms-us.indegene.com/Gilead/Banner/GFC-15565/HTML/CFF_Round1/300x250/index.html","client":"Gilead","dimensions":"300x250"},
    {"url_id":"6","name":"Bayer CS · Kerendia CKD HCP 300x600",
     "url":"https://lms-us.indegene.com/Bayer_CS/Banners/PID-8417_PP-KER-US-3962-1_KER_CKD_HCP_ACC_2026_Digital_Banner/300x600/index.html","client":"Bayer CS","dimensions":"300x600"},
    {"url_id":"7","name":"Bayer CS · Kerendia CKD HCP 160x600",
     "url":"https://lms-us.indegene.com/Bayer_CS/Banners/PID-8417_PP-KER-US-3962-1_KER_CKD_HCP_ACC_2026_Digital_Banner/160x600/index.html","client":"Bayer CS","dimensions":"160x600"},
    {"url_id":"8","name":"Bayer CS · Kerendia CKD HCP 728x90",
     "url":"https://lms-us.indegene.com/Bayer_CS/Banners/PID-8417_PP-KER-US-3962-1_KER_CKD_HCP_ACC_2026_Digital_Banner/728x90/index.html","client":"Bayer CS","dimensions":"728x90"},
    {"url_id":"10","name":"Gilead GFC-16799 · HCP Non-Branded 300x250",
     "url":"https://lms-us.indegene.com/Gilead/Banner/GFC-16799/HTML/CFF_Round1/english_us_unbp_3672_hcp_nonbranded_goldconference_na_html_reviewthedata_livdelzi_300x250/index.html","client":"Gilead","dimensions":"300x250"},
]

async def seed():
    await init_db()
    async with AsyncSessionLocal() as db:
        for b in BANNERS:
            ex = await db.execute(select(Banner).where(Banner.url_id == b["url_id"]))
            if ex.scalar_one_or_none():
                print(f"  skip: {b['name']}")
                continue
            db.add(Banner(**b))
            print(f"  added: {b['name']}")
        await db.commit()
    print("Seed complete.")

if __name__ == "__main__":
    asyncio.run(seed())
