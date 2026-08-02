"""Approved, non-sensitive initial knowledge. This module contains no secrets."""

from __future__ import annotations

from typing import Any, Dict, List


OFFICIAL_SOURCE = "approved_creator_and_repository_inspection_2026-07-31"


def _record(
    key: str,
    category: str,
    title: str,
    content_en: str,
    content_ar: str,
    content_tr: str,
    structured_data: Dict[str, Any],
    priority: int,
) -> Dict[str, Any]:
    return {
        "key": key,
        "category": category,
        "title": title,
        "content": content_en,
        "content_en": content_en,
        "content_ar": content_ar,
        "content_tr": content_tr,
        "structured_data": structured_data,
        "visibility": "public",
        "priority": priority,
        "source": OFFICIAL_SOURCE,
    }


OFFICIAL_KNOWLEDGE: List[Dict[str, Any]] = [
    _record(
        "aegis.project.identity",
        "project_profile",
        "AegisAI project identity",
        "AegisAI is an AI-assisted security operations and smart-city risk-intelligence platform. It analyzes authorized camera feeds, detects and tracks activity, helps organize evidence, prioritizes events for review, and assists authorized operators in understanding situations and making informed decisions.",
        "AegisAI هو نظام ذكي مساعد لعمليات الأمن وتحليل المخاطر في المدن الذكية. يحلل بث الكاميرات المصرح بها، ويكتشف الأنشطة ويتتبعها، ويساعد في تنظيم الأدلة وترتيب الأحداث للمراجعة، ويمكّن المشغلين المصرح لهم من فهم الحالات واتخاذ قرارات مبنية على المعلومات.",
        "AegisAI, yetkili kamera akışlarını analiz eden, etkinlikleri tespit edip takip eden, kanıtları düzenlemeye yardımcı olan ve yetkili operatörlerin bilinçli kararlar almasını destekleyen yapay zekâ destekli bir güvenlik operasyonları ve akıllı şehir risk istihbaratı platformudur.",
        {"kind": "project_identity", "operator_role": "authorized operators", "aliases": ["what is aegis", "aegisai", "what does aegis do", "aegis nedir", "ما هو aegis"]},
        1000,
    ),
    _record(
        "aegis.project.purpose",
        "project_purpose",
        "AegisAI purpose",
        "AegisAI assists authorized operators with evidence organization, event prioritization, and informed decision-making. It does not make autonomous enforcement decisions.",
        "يساعد AegisAI المشغلين المصرح لهم في تنظيم الأدلة وترتيب الأحداث واتخاذ قرارات مبنية على المعلومات. ولا يتخذ قرارات إنفاذ ذاتية.",
        "AegisAI, yetkili operatörlere kanıtları düzenleme, olayları önceliklendirme ve bilinçli karar alma konusunda yardımcı olur. Otonom yaptırım kararları vermez.",
        {"kind": "project_purpose", "aliases": ["purpose", "mission", "why aegis", "amaç", "هدف"]},
        950,
    ),
    _record(
        "aegis.creator.profile",
        "creator_profile",
        "AegisAI creator",
        "AegisAI was created and designed by Hassan, AI/software developer.",
        "تم إنشاء وتصميم نظام AegisAI بواسطة حسان، مطور برمجيات وذكاء اصطناعي.",
        "AegisAI, yapay zekâ/yazılım geliştiricisi Hassan tarafından oluşturulmuş ve tasarlanmıştır.",
        {"kind": "creator_profile", "display_name": "Hassan", "aliases": ["who created aegis", "who designed aegis", "hassan", "creator", "created", "designed", "من أنشأ", "من صمم", "kim oluşturdu", "kim tasarladı"]},
        1000,
    ),
    _record(
        "aegis.creator.contributions",
        "creator_contributions",
        "Hassan's AegisAI contributions",
        "Hassan worked on the overall AegisAI system architecture, backend, computer-vision detection and tracking pipeline, risk analysis and event intelligence, tracking workflows, semantic evidence search, AI assistant and chat/voice interaction, operations dashboard, and real-time communication and operator-focused workflows.",
        "عمل حسان على البنية العامة لنظام AegisAI، والواجهة الخلفية، وخط معالجة الكشف والتتبع بالرؤية الحاسوبية، وتحليل المخاطر وذكاء الأحداث، وسير عمل التتبع، والبحث الدلالي في الأدلة، والمساعد الذكي وتفاعل الدردشة/الصوت، ولوحة العمليات، والاتصال الفوري وسير العمل الموجّه للمشغلين.",
        "Hassan; genel AegisAI sistem mimarisi, arka uç, bilgisayarlı görü tespit ve takip hattı, risk analizi ve olay istihbaratı, takip iş akışları, anlamsal kanıt arama, yapay zekâ asistanı ile sohbet/ses etkileşimi, operasyon panosu ve gerçek zamanlı iletişim ile operatör odaklı iş akışları üzerinde çalıştı.",
        {"kind": "creator_contributions", "contributions": ["system architecture", "backend", "computer-vision detection and tracking pipeline", "risk analysis and event intelligence", "tracking workflows", "semantic evidence search", "AI assistant and chat/voice interaction", "operations dashboard", "real-time communication and operator-focused workflows"], "aliases": ["what did hassan do", "hassan contribution", "contributions", "worked on", "ماذا فعل حسان", "مساهمات", "hassan ne yaptı", "katkı"]},
        990,
    ),
    _record(
        "aegis.project.architecture",
        "project_architecture",
        "AegisAI architecture overview",
        "The repository implements a Python FastAPI backend, SQLAlchemy persistence, a computer-vision processing pipeline, API routes, and a Next.js operator frontend. These components exchange source-backed operational data for authorized operator workflows.",
        "يحتوي المستودع على واجهة خلفية Python FastAPI، وتخزين SQLAlchemy، وخط معالجة للرؤية الحاسوبية، ومسارات API، وواجهة مشغل Next.js. وتتبادل هذه المكونات بيانات تشغيلية قائمة على المصادر لسير عمل المشغلين المصرح لهم.",
        "Depo; Python FastAPI arka ucu, SQLAlchemy kalıcılığı, bilgisayarlı görü işleme hattı, API rotaları ve Next.js operatör arayüzü içerir. Bu bileşenler, yetkili operatör iş akışları için kaynak destekli operasyonel veri alışverişi yapar.",
        {"kind": "architecture", "components": ["FastAPI backend", "SQLAlchemy persistence", "computer-vision pipeline", "API routes", "Next.js operator frontend"], "aliases": ["architecture", "how is aegis built", "backend frontend", "mimari", "بنية"]},
        900,
    ),
    _record(
        "aegis.project.computer_vision",
        "project_capabilities",
        "Computer-vision capabilities",
        "AegisAI processes authorized camera feeds to detect and track activity. Detection, tracking, risk analysis, and event intelligence are separate capabilities that provide information for authorized operator review.",
        "يعالج AegisAI بث الكاميرات المصرح بها لاكتشاف الأنشطة وتتبعها. ويُعد الكشف والتتبع وتحليل المخاطر وذكاء الأحداث قدرات منفصلة تقدم معلومات لمراجعة المشغلين المصرح لهم.",
        "AegisAI, yetkili kamera akışlarını etkinlik tespiti ve takibi için işler. Tespit, takip, risk analizi ve olay istihbaratı; yetkili operatör incelemesi için bilgi sağlayan ayrı yeteneklerdir.",
        {"kind": "capability", "capabilities": ["authorized camera feed processing", "detection", "tracking", "risk analysis", "event intelligence"], "aliases": ["computer vision", "detection", "tracking", "camera feeds", "رؤية حاسوبية", "كشف", "takip", "bilgisayarlı görü"]},
        880,
    ),
    _record(
        "aegis.project.ai_assistant",
        "project_capabilities",
        "AI assistant capabilities",
        "AegisAI includes an AI assistant for authorized operator chat and voice interaction. The assistant is grounded in verified system data and does not make autonomous enforcement decisions.",
        "يتضمن AegisAI مساعدًا ذكيًا لتفاعل الدردشة والصوت للمشغلين المصرح لهم. ويستند المساعد إلى بيانات نظام موثقة ولا يتخذ قرارات إنفاذ ذاتية.",
        "AegisAI, yetkili operatör sohbeti ve ses etkileşimi için bir yapay zekâ asistanı içerir. Asistan doğrulanmış sistem verilerine dayanır ve otonom yaptırım kararları vermez.",
        {"kind": "capability", "capabilities": ["operator chat", "voice interaction", "verified system-data grounding"], "aliases": ["ai assistant", "chat", "voice", "gemini", "مساعد", "صوت", "yapay zekâ", "ses"]},
        870,
    ),
    _record(
        "aegis.project.security",
        "project_security",
        "Security and authorization principles",
        "AegisAI is designed for authorized camera feeds and authorized operators. The API uses server-side API-key authentication, and administrative knowledge changes require a separate server-side administrator credential.",
        "صُمم AegisAI لبث الكاميرات والمشغلين المصرح لهم. وتستخدم الواجهة البرمجية مصادقة مفتاح API على الخادم، وتتطلب تغييرات المعرفة الإدارية بيانات اعتماد منفصلة للمسؤول على الخادم.",
        "AegisAI, yetkili kamera akışları ve yetkili operatörler için tasarlanmıştır. API, sunucu tarafı API anahtarı kimlik doğrulaması kullanır; yönetimsel bilgi değişiklikleri ayrı bir sunucu tarafı yönetici kimlik bilgisi gerektirir.",
        {"kind": "security", "principles": ["authorized feeds", "authorized operators", "server-side API key", "separate administrator credential"], "aliases": ["security", "authorization", "rbac", "permissions", "أمان", "صلاحيات", "güvenlik", "yetkilendirme"]},
        860,
    ),
    _record(
        "aegis.project.technology",
        "project_technology",
        "Repository-verified technology stack",
        "Implemented in the repository: Python, FastAPI, SQLAlchemy, Alembic, Pydantic, Next.js, React, TypeScript, Ultralytics YOLO, and OpenCV. Configured but optional: PostgreSQL, Redis, Google Gemini, and the semantic vision runtime. Technology availability depends on deployment configuration and installed dependencies.",
        "المكوّنات المطبقة في المستودع: Python وFastAPI وSQLAlchemy وAlembic وPydantic وNext.js وReact وTypeScript وUltralytics YOLO وOpenCV. والمكونات المهيأة لكنها اختيارية: PostgreSQL وRedis وGoogle Gemini وبيئة الرؤية الدلالية. يعتمد توفر التقنية على إعدادات النشر والتبعيات المثبتة.",
        "Depoda uygulanmış teknolojiler: Python, FastAPI, SQLAlchemy, Alembic, Pydantic, Next.js, React, TypeScript, Ultralytics YOLO ve OpenCV. Yapılandırılmış ancak isteğe bağlı olanlar: PostgreSQL, Redis, Google Gemini ve anlamsal görü çalışma zamanı. Teknoloji kullanılabilirliği dağıtım yapılandırmasına ve kurulu bağımlılıklara bağlıdır.",
        {"kind": "technology_stack", "technologies": [{"name": "Python", "status": "implemented", "verified_by": ["source code"]}, {"name": "FastAPI", "status": "implemented", "verified_by": ["requirements.txt", "aegis/api/app.py"]}, {"name": "SQLAlchemy", "status": "implemented", "verified_by": ["requirements.txt", "aegis/database"]}, {"name": "Alembic", "status": "implemented", "verified_by": ["requirements.txt", "alembic.ini"]}, {"name": "Pydantic", "status": "implemented", "verified_by": ["requirements.txt", "aegis/ai/schemas.py"]}, {"name": "Next.js", "status": "implemented", "verified_by": ["frontend/package.json"]}, {"name": "React", "status": "implemented", "verified_by": ["frontend/package.json"]}, {"name": "TypeScript", "status": "implemented", "verified_by": ["frontend/package.json"]}, {"name": "Ultralytics YOLO", "status": "implemented", "verified_by": ["requirements.txt", "aegis/pipeline"]}, {"name": "OpenCV", "status": "implemented", "verified_by": ["requirements.txt"]}, {"name": "PostgreSQL", "status": "configured_optional", "verified_by": [".env.example", "aegis/database/connection.py"]}, {"name": "Redis", "status": "configured_optional", "verified_by": ["requirements.txt", ".env.example"]}, {"name": "Google Gemini", "status": "configured_optional", "verified_by": ["requirements.txt", "aegis/intelligence/live_service.py"]}, {"name": "semantic vision runtime", "status": "configured_optional", "verified_by": [".env.example", "aegis/semantic"]}], "aliases": ["technologies", "technology stack", "tech stack", "what is used", "hangi teknolojiler", "teknoloji", "التقنيات", "تكنولوجيا"]},
        920,
    ),
    _record(
        "aegis.project.limitations",
        "project_limitations",
        "Known limitations",
        "AegisAI availability depends on configured and running camera, pipeline, database, cache, model, and AI-provider services. Optional capabilities remain unavailable until configured. AegisAI assists authorized operators and does not make autonomous enforcement decisions.",
        "يعتمد توفر AegisAI على إعداد وتشغيل خدمات الكاميرا وخط المعالجة وقاعدة البيانات وذاكرة التخزين المؤقت والنموذج ومزود الذكاء الاصطناعي. وتبقى القدرات الاختيارية غير متاحة حتى يتم إعدادها. يساعد AegisAI المشغلين المصرح لهم ولا يتخذ قرارات إنفاذ ذاتية.",
        "AegisAI kullanılabilirliği; kamera, işlem hattı, veritabanı, önbellek, model ve yapay zekâ sağlayıcısı hizmetlerinin yapılandırılıp çalışmasına bağlıdır. İsteğe bağlı yetenekler yapılandırılana kadar kullanılamaz. AegisAI yetkili operatörlere yardımcı olur ve otonom yaptırım kararları vermez.",
        {"kind": "limitations", "limitations": ["deployment-dependent availability", "optional capabilities require configuration", "no autonomous enforcement decisions"], "aliases": ["limitations", "known limitations", "what cannot aegis do", "limits", "قيود", "محدوديات", "sınırlamalar"]},
        850,
    ),
]
