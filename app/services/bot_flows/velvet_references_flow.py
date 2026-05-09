from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.services.bot_flows.base import BaseBotFlow, BotFlowContext, BotFlowResult


class VelvetReferencesFlow(BaseBotFlow):
    code = "velvet_references"

    def references_enabled(self, ctx: BotFlowContext) -> bool:
        return bool({"references", "ref", "referencias"}.intersection(ctx.enabled_modules))

    async def can_handle(self, ctx: BotFlowContext) -> bool:
        return self.references_enabled(ctx)

    def txt(self, language: str, key: str, **kwargs: Any) -> str:
        lang = (language or "es").lower()

        texts = {
            "es": {
                "pick_start": "🧵 Selecciona la referencia para iniciar turno.",
                "pick_switch": "🔁 Selecciona la nueva referencia.",
                "pick_close": "✅ Selecciona la referencia que vas a cerrar.",
                "pick_size": "📏 Selecciona la talla.",
                "ask_total": "🔢 Escribe el total terminado para {name} / talla {size}.",
                "no_refs": "No hay referencias activas para bot.",
                "started": "✅ Turno iniciado en referencia: {name}.",
                "switched": "🔁 Cambio de referencia registrado: {name}.",
                "closed": "✅ Producción cerrada: {name} / {size} / total {qty}.",
                "invalid_total": "Escribe solo el número total terminado.",
                "btn_switch": "🔁 Cambiar referencia",
                "btn_close": "✅ Cerrar referencia",
            },
            "en": {
                "pick_start": "🧵 Select the reference to start your shift.",
                "pick_switch": "🔁 Select the new reference.",
                "pick_close": "✅ Select the reference to close.",
                "pick_size": "📏 Select size.",
                "ask_total": "🔢 Type the finished total for {name} / size {size}.",
                "no_refs": "There are no bot-active references.",
                "started": "✅ Shift started on reference: {name}.",
                "switched": "🔁 Reference change saved: {name}.",
                "closed": "✅ Production closed: {name} / {size} / total {qty}.",
                "invalid_total": "Type only the finished total number.",
                "btn_switch": "🔁 Change reference",
                "btn_close": "✅ Close reference",
            },
            "fr": {
                "pick_start": "🧵 Sélectionnez la référence pour commencer.",
                "pick_switch": "🔁 Sélectionnez la nouvelle référence.",
                "pick_close": "✅ Sélectionnez la référence à clôturer.",
                "pick_size": "📏 Sélectionnez la taille.",
                "ask_total": "🔢 Écrivez le total terminé pour {name} / taille {size}.",
                "no_refs": "Aucune référence active dans le bot.",
                "started": "✅ Service démarré sur la référence : {name}.",
                "switched": "🔁 Changement de référence enregistré : {name}.",
                "closed": "✅ Production clôturée : {name} / {size} / total {qty}.",
                "invalid_total": "Écrivez seulement le nombre total terminé.",
                "btn_switch": "🔁 Changer référence",
                "btn_close": "✅ Clôturer référence",
            },
        }

        template = texts.get(lang, texts["es"]).get(key, key)
        return template.format(**kwargs)

    async def bot_references(self, db: Any, company_id: str) -> list[dict[str, Any]]:
        result = await db.execute(
            text("""
                SELECT min(id)::text AS id, name, count(*) AS sizes_count
                FROM product_references
                WHERE company_id = :company_id
                  AND bot_active IS TRUE
                GROUP BY name
                ORDER BY name ASC
                LIMIT 50
            """),
            {"company_id": company_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def reference_by_id(self, db: Any, company_id: str, reference_id: str) -> dict[str, Any] | None:
        result = await db.execute(
            text("""
                SELECT id::text AS id, name, size
                FROM product_references
                WHERE company_id = :company_id
                  AND id = :reference_id
                  AND bot_active IS TRUE
                LIMIT 1
            """),
            {"company_id": company_id, "reference_id": reference_id},
        )
        row = result.mappings().first()
        return dict(row) if row else None

    async def sizes_by_name(self, db: Any, company_id: str, name: str) -> list[dict[str, Any]]:
        result = await db.execute(
            text("""
                SELECT id::text AS id, name, size
                FROM product_references
                WHERE company_id = :company_id
                  AND lower(name) = lower(:name)
                  AND bot_active IS TRUE
                ORDER BY size ASC
                LIMIT 50
            """),
            {"company_id": company_id, "name": name},
        )
        return [dict(row) for row in result.mappings().all()]

    def reference_keyboard(self, rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
        keyboard = []

        for row in rows:
            name = str(row.get("name") or "").strip()
            reference_id = str(row.get("id") or "").strip()

            if name and reference_id:
                keyboard.append([
                    {
                        "text": name[:60],
                        "callback_data": f"{prefix}:{reference_id}",
                    }
                ])

        return {"inline_keyboard": keyboard}

    def size_keyboard(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        keyboard = []

        for row in rows:
            size = str(row.get("size") or "").strip()
            reference_id = str(row.get("id") or "").strip()

            if size and reference_id:
                keyboard.append([
                    {
                        "text": size[:60],
                        "callback_data": f"clx:velvet:close_size:{reference_id}",
                    }
                ])

        return {"inline_keyboard": keyboard}

    async def start_reference_session(
        self,
        db: Any,
        *,
        ctx: BotFlowContext,
        reference_id: str,
        close_status: str,
    ) -> dict[str, Any]:
        ref = await self.reference_by_id(db, ctx.company_id, reference_id)

        if not ref:
            return {"ok": False, "error": "reference_not_found"}

        await db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS reference_work_sessions (
                    id text PRIMARY KEY,
                    company_id text NOT NULL,
                    employee_id text NOT NULL,
                    employee_name text NULL,
                    telegram_user_id text NULL,
                    reference_id text NULL,
                    reference_name text NOT NULL,
                    started_at timestamptz NOT NULL DEFAULT now(),
                    ended_at timestamptz NULL,
                    duration_minutes numeric NOT NULL DEFAULT 0,
                    status text NOT NULL DEFAULT 'active',
                    source_channel text NOT NULL DEFAULT 'telegram',
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """)
        )

        await db.execute(
            text("""
                UPDATE reference_work_sessions
                SET
                    ended_at = now(),
                    duration_minutes = GREATEST(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 0),
                    status = :close_status,
                    updated_at = now()
                WHERE company_id = :company_id
                  AND employee_id = :employee_id
                  AND status = 'active'
            """),
            {
                "company_id": ctx.company_id,
                "employee_id": ctx.employee_id,
                "close_status": close_status,
            },
        )

        await db.execute(
            text("""
                INSERT INTO reference_work_sessions (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    started_at,
                    status,
                    source_channel,
                    created_at,
                    updated_at
                )
                VALUES (
                    gen_random_uuid()::text,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    now(),
                    'active',
                    'telegram',
                    now(),
                    now()
                )
            """),
            {
                "company_id": ctx.company_id,
                "employee_id": ctx.employee_id,
                "employee_name": ctx.employee_name,
                "telegram_user_id": ctx.telegram_user_id,
                "reference_id": ref["id"],
                "reference_name": ref["name"],
            },
        )

        return {"ok": True, "reference": ref}

    async def save_production_close(
        self,
        db: Any,
        *,
        ctx: BotFlowContext,
        reference_id: str,
        quantity_finished: int,
    ) -> dict[str, Any]:
        ref = await self.reference_by_id(db, ctx.company_id, reference_id)

        if not ref:
            return {"ok": False, "error": "reference_not_found"}

        await db.execute(
            text("""
                CREATE TABLE IF NOT EXISTS reference_production_closures (
                    id text PRIMARY KEY,
                    company_id text NOT NULL,
                    employee_id text NOT NULL,
                    employee_name text NULL,
                    telegram_user_id text NULL,
                    reference_id text NULL,
                    reference_name text NOT NULL,
                    size text NOT NULL,
                    quantity_finished integer NOT NULL DEFAULT 0,
                    notes text NULL,
                    closed_at timestamptz NOT NULL DEFAULT now(),
                    source_channel text NOT NULL DEFAULT 'telegram',
                    created_at timestamptz NOT NULL DEFAULT now()
                )
            """)
        )

        await db.execute(
            text("""
                INSERT INTO reference_production_closures (
                    id,
                    company_id,
                    employee_id,
                    employee_name,
                    telegram_user_id,
                    reference_id,
                    reference_name,
                    size,
                    quantity_finished,
                    closed_at,
                    source_channel,
                    created_at
                )
                VALUES (
                    gen_random_uuid()::text,
                    :company_id,
                    :employee_id,
                    :employee_name,
                    :telegram_user_id,
                    :reference_id,
                    :reference_name,
                    :size,
                    :quantity_finished,
                    now(),
                    'telegram',
                    now()
                )
            """),
            {
                "company_id": ctx.company_id,
                "employee_id": ctx.employee_id,
                "employee_name": ctx.employee_name,
                "telegram_user_id": ctx.telegram_user_id,
                "reference_id": ref["id"],
                "reference_name": ref["name"],
                "size": ref["size"],
                "quantity_finished": int(quantity_finished),
            },
        )

        return {"ok": True, "reference": ref, "quantity_finished": int(quantity_finished)}

    async def handle(self, db: Any, ctx: BotFlowContext, update_data: dict[str, Any]) -> BotFlowResult:
        raw = str(update_data.get("text") or "").strip()
        raw_lower = raw.lower()

        if raw_lower in {"clx:cmd:entrada", "/entrada", "/inicio", "inicio", "iniciar turno"}:
            refs = await self.bot_references(db, ctx.company_id)

            if not refs:
                return BotFlowResult(
                    handled=True,
                    ok=False,
                    action="references_empty",
                    reply_text=self.txt(ctx.language, "no_refs"),
                )

            return BotFlowResult(
                handled=True,
                ok=True,
                action="reference_start_prompt",
                reply_text=self.txt(ctx.language, "pick_start"),
                reply_markup=self.reference_keyboard(refs, "clx:velvet:start"),
            )

        if raw_lower == "clx:velvet:switch":
            refs = await self.bot_references(db, ctx.company_id)

            return BotFlowResult(
                handled=True,
                ok=True,
                action="reference_switch_prompt",
                reply_text=self.txt(ctx.language, "pick_switch"),
                reply_markup=self.reference_keyboard(refs, "clx:velvet:switch"),
            )

        if raw_lower == "clx:velvet:close":
            refs = await self.bot_references(db, ctx.company_id)

            return BotFlowResult(
                handled=True,
                ok=True,
                action="reference_close_prompt",
                reply_text=self.txt(ctx.language, "pick_close"),
                reply_markup=self.reference_keyboard(refs, "clx:velvet:close_ref"),
            )

        return BotFlowResult(handled=False)
