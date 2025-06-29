from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import desc, func, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import AnalysisHistory, User


class AnalysisHistoryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_analysis_record(
        self,
        user_id: int,
        device_model: Optional[str] = None,
        ios_version: Optional[str] = None,
        original_filename: Optional[str] = None,
        file_type: str = "unknown",
        file_size: Optional[int] = None,
        file_path: Optional[str] = None,
        file_hash: Optional[str] = None,
        error_code: Optional[str] = None,
        error_description: Optional[str] = None,
        solution_text: Optional[str] = None,
        is_solution_found: bool = False,
        tokens_used: int = 0
    ) -> AnalysisHistory:
        """Создать новую запись анализа"""
        analysis = AnalysisHistory(
            user_id=user_id,
            device_model=device_model,
            ios_version=ios_version,
            original_filename=original_filename,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            file_hash=file_hash,
            error_code=error_code,
            error_description=error_description,
            solution_text=solution_text,
            is_solution_found=is_solution_found,
            tokens_used=tokens_used
        )
        
        self.session.add(analysis)
        await self.session.commit()
        await self.session.refresh(analysis)
        return analysis

    async def get_user_history(
        self,
        user_id: int,
        page: int = 0,
        page_size: int = 10,
        file_type_filter: Optional[str] = None,
        success_filter: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Получить историю анализов пользователя с пагинацией и фильтрами"""
        query = select(AnalysisHistory).filter(
            AnalysisHistory.user_id == user_id
        )
        
        # Применяем фильтры
        if file_type_filter:
            query = query.filter(AnalysisHistory.file_type == file_type_filter)
        
        if success_filter is not None:
            query = query.filter(AnalysisHistory.is_solution_found == success_filter)
        
        if date_from:
            query = query.filter(AnalysisHistory.created_at >= date_from)
        
        if date_to:
            query = query.filter(AnalysisHistory.created_at <= date_to)
        
        # Подсчет общего количества
        count_query = select(func.count(AnalysisHistory.id)).filter(
            AnalysisHistory.user_id == user_id
        )
        if file_type_filter:
            count_query = count_query.filter(AnalysisHistory.file_type == file_type_filter)
        if success_filter is not None:
            count_query = count_query.filter(AnalysisHistory.is_solution_found == success_filter)
        if date_from:
            count_query = count_query.filter(AnalysisHistory.created_at >= date_from)
        if date_to:
            count_query = count_query.filter(AnalysisHistory.created_at <= date_to)
            
        total_count = await self.session.scalar(count_query)
        
        # Получаем записи с пагинацией
        analyses_result = await self.session.execute(
            query.order_by(desc(AnalysisHistory.created_at))
            .offset(page * page_size)
            .limit(page_size)
        )
        analyses = analyses_result.scalars().all()
        
        return {
            "analyses": analyses,
            "total_count": total_count or 0,
            "page": page,
            "page_size": page_size,
            "total_pages": ((total_count or 0) + page_size - 1) // page_size
        }

    async def get_analysis_by_id(self, analysis_id: int, user_id: int) -> Optional[AnalysisHistory]:
        """Получить анализ по ID (только для конкретного пользователя)"""
        result = await self.session.execute(
            select(AnalysisHistory).filter(
                and_(
                    AnalysisHistory.id == analysis_id,
                    AnalysisHistory.user_id == user_id
                )
            )
        )
        return result.scalars().first()

    async def delete_analysis(self, analysis_id: int, user_id: int) -> bool:
        """Удалить анализ (только для конкретного пользователя)"""
        analysis = await self.get_analysis_by_id(analysis_id, user_id)
        if analysis:
            await self.session.delete(analysis)
            await self.session.commit()
            return True
        return False

    async def get_user_statistics(self, user_id: int) -> Dict[str, Any]:
        """Получить статистику анализов пользователя"""
        # Общее количество анализов
        total_analyses = await self.session.scalar(
            select(func.count(AnalysisHistory.id))
            .filter(AnalysisHistory.user_id == user_id)
        )
        
        # Успешные анализы
        successful_analyses = await self.session.scalar(
            select(func.count(AnalysisHistory.id))
            .filter(
                and_(
                    AnalysisHistory.user_id == user_id,
                    AnalysisHistory.is_solution_found == True
                )
            )
        )
        
        # Потраченные токены
        total_tokens = await self.session.scalar(
            select(func.sum(AnalysisHistory.tokens_used))
            .filter(AnalysisHistory.user_id == user_id)
        ) or 0
        
        # Анализы по типам файлов
        file_types_result = await self.session.execute(
            select(
                AnalysisHistory.file_type,
                func.count(AnalysisHistory.id).label('count')
            )
            .filter(AnalysisHistory.user_id == user_id)
            .group_by(AnalysisHistory.file_type)
        )
        file_types = {row[0]: row[1] for row in file_types_result}
        
        total_analyses_value = total_analyses or 0
        successful_analyses_value = successful_analyses or 0
        
        return {
            "total_analyses": total_analyses_value,
            "successful_analyses": successful_analyses_value,
            "failed_analyses": total_analyses_value - successful_analyses_value,
            "success_rate": (successful_analyses_value / total_analyses_value * 100) if total_analyses_value else 0,
            "total_tokens_used": total_tokens,
            "file_types": file_types
        }

    async def cleanup_old_analyses(self, days_to_keep: int = 30) -> int:
        """Удалить старые анализы (автоматическая очистка)"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(AnalysisHistory.created_at < cutoff_date)
        )
        old_analyses = result.scalars().all()
        
        deleted_count = len(old_analyses)
        for analysis in old_analyses:
            await self.session.delete(analysis)
        
        await self.session.commit()
        return deleted_count

    async def get_recent_analyses_summary(self, user_id: int, limit: int = 3) -> List[AnalysisHistory]:
        """Получить краткую сводку последних анализов для отображения в профиле"""
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(AnalysisHistory.user_id == user_id)
            .order_by(desc(AnalysisHistory.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def clear_user_history(self, user_id: int) -> int:
        """Очистить всю историю анализов пользователя"""
        # Получаем все анализы пользователя
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(AnalysisHistory.user_id == user_id)
        )
        analyses = result.scalars().all()
        
        deleted_count = len(analyses)
        
        # Удаляем все анализы
        for analysis in analyses:
            await self.session.delete(analysis)
        
        await self.session.commit()
        return deleted_count

    async def can_repeat_analysis(self, analysis_id: int, user_id: int) -> tuple[bool, Optional[str]]:
        """
        Проверить, можно ли повторить анализ.
        Возвращает (можно_ли, сообщение_об_ошибке)
        """
        analysis = await self.get_analysis_by_id(analysis_id, user_id)
        if not analysis:
            return False, "Analysis not found"
        
        # Проверяем, заблокирован ли анализ
        if analysis.blocked_until:
            now = datetime.utcnow()
            if now < analysis.blocked_until:
                # Вычисляем оставшее время
                remaining = analysis.blocked_until - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                if hours > 0:
                    time_left = f"{hours} ч {minutes} мин"
                else:
                    time_left = f"{minutes} мин"
                return False, f"Попробуйте снова через {time_left}"
        
        # Проверяем количество попыток
        if analysis.repeat_attempts >= 2:
            # Если прошло больше 3 часов с последнего круга, сбрасываем счетчик
            if analysis.last_repeat_attempt:
                time_since_last = datetime.utcnow() - analysis.last_repeat_attempt
                if time_since_last >= timedelta(hours=3):
                    # Сбрасываем счетчик
                    analysis.repeat_attempts = 0
                    analysis.blocked_until = None
                    await self.session.commit()
                    return True, None
            
            return False, "Достигнут лимит попыток (2). Попробуйте снова через 3 часа"
        
        return True, None

    async def increment_repeat_attempts(self, analysis_id: int, user_id: int) -> bool:
        """
        Увеличить счетчик попыток повторного анализа.
        Блокирует анализ на 3 часа после второго неудачного круга.
        """
        analysis = await self.get_analysis_by_id(analysis_id, user_id)
        if not analysis:
            return False
        
        analysis.repeat_attempts += 1
        analysis.last_repeat_attempt = datetime.utcnow()
        
        # Если достигли лимита попыток, блокируем на 3 часа
        if analysis.repeat_attempts >= 2:
            analysis.blocked_until = datetime.utcnow() + timedelta(hours=3)
        
        await self.session.commit()
        return True

    async def reset_repeat_attempts(self, analysis_id: int, user_id: int) -> bool:
        """
        Сбросить счетчик попыток (например, при успешном анализе).
        """
        analysis = await self.get_analysis_by_id(analysis_id, user_id)
        if not analysis:
            return False
        
        analysis.repeat_attempts = 0
        analysis.last_repeat_attempt = None
        analysis.blocked_until = None
        
        await self.session.commit()
        return True 

    async def can_analyze_file_by_hash(self, user_id: int, file_hash: str) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Проверить, можно ли анализировать файл по его хешу.
        Возвращает (можно_ли, сообщение_об_ошибке, analysis_id_последней_записи)
        """
        if not file_hash:
            return True, None, None
        
        # Ищем последнюю запись этого файла у пользователя
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(
                and_(
                    AnalysisHistory.user_id == user_id,
                    AnalysisHistory.file_hash == file_hash
                )
            )
            .order_by(desc(AnalysisHistory.created_at))
            .limit(1)
        )
        analysis = result.scalars().first()
        
        if not analysis:
            return True, None, None
        
        # Если файл уже успешно проанализирован, не ограничиваем
        if analysis.is_solution_found:
            return True, None, analysis.id
        
        # Проверяем блокировку
        if analysis.blocked_until:
            now = datetime.utcnow()
            if now < analysis.blocked_until:
                remaining = analysis.blocked_until - now
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                if hours > 0:
                    time_left = f"{hours} ч {minutes} мин"
                else:
                    time_left = f"{minutes} мин"
                return False, f"Этот файл заблокирован для повторного анализа. Попробуйте снова через {time_left}", analysis.id
        
        # Проверяем количество попыток
        if analysis.repeat_attempts >= 2:
            # Если прошло больше 3 часов с последнего круга, сбрасываем счетчик
            if analysis.last_repeat_attempt:
                time_since_last = datetime.utcnow() - analysis.last_repeat_attempt
                if time_since_last >= timedelta(hours=3):
                    # Сбрасываем счетчик
                    analysis.repeat_attempts = 0
                    analysis.blocked_until = None
                    await self.session.commit()
                    return True, None, analysis.id
            
            return False, f"Достигнут лимит кругов анализа для этого файла (2). Попробуйте снова через 3 часа", analysis.id
        
        return True, None, analysis.id

    async def increment_attempts_by_hash(self, user_id: int, file_hash: str) -> bool:
        """
        Увеличить счетчик попыток для файла по хешу.
        """
        if not file_hash:
            return False
        
        # Ищем последнюю запись этого файла у пользователя
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(
                and_(
                    AnalysisHistory.user_id == user_id,
                    AnalysisHistory.file_hash == file_hash
                )
            )
            .order_by(desc(AnalysisHistory.created_at))
            .limit(1)
        )
        analysis = result.scalars().first()
        
        if not analysis:
            return False
        
        analysis.repeat_attempts += 1
        analysis.last_repeat_attempt = datetime.utcnow()
        
        # Если достигли лимита попыток, блокируем на 3 часа
        if analysis.repeat_attempts >= 2:
            analysis.blocked_until = datetime.utcnow() + timedelta(hours=3)
        
        await self.session.commit()
        return True

    async def reset_attempts_by_hash(self, user_id: int, file_hash: str) -> bool:
        """
        Сбросить счетчик попыток для файла по хешу (при успешном анализе).
        """
        if not file_hash:
            return False
        
        # Ищем все записи этого файла у пользователя и сбрасываем счетчики
        result = await self.session.execute(
            select(AnalysisHistory)
            .filter(
                and_(
                    AnalysisHistory.user_id == user_id,
                    AnalysisHistory.file_hash == file_hash
                )
            )
        )
        analyses = result.scalars().all()
        
        for analysis in analyses:
            analysis.repeat_attempts = 0
            analysis.last_repeat_attempt = None
            analysis.blocked_until = None
        
        await self.session.commit()
        return len(analyses) > 0