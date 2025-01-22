from db import Roles

def calculate_attention_score(current_score, is_correct_answer, total_polls, correct_answers):
    """
    Расчет коэффициента внимательности
    
    Args:
        current_score (float): Текущий коэффициент внимательности
        is_correct_answer (bool): Правильность текущего ответа
        total_polls (int): Общее количество опросов
        correct_answers (int): Количество правильных ответов
    
    Returns:
        float: Новый коэффициент внимательности
    """
    # Базовые параметры настройки
    BASE_SCORE = 1.0  # Начальный коэффициент
    MAX_SCORE = 1.0   # Максимальный коэффициент
    MIN_SCORE = 0.5   # Минимальный коэффициент
    
    # Коэффициенты влияния
    CORRECT_ANSWER_BONUS = 0.1  # Бонус за правильный ответ
    INCORRECT_ANSWER_PENALTY = 0.05  # Штраф за неправильный ответ
    
    # Расчет процента правильных ответов
    correct_percentage = (correct_answers / total_polls) * 100 if total_polls > 0 else 0
    
    # Динамическая корректировка коэффициента
    if is_correct_answer:
        # Бонус за правильный ответ с учетом текущей статистики
        new_score = min(
            current_score + CORRECT_ANSWER_BONUS * (1 + correct_percentage / 100), 
            MAX_SCORE
        )
    else:
        # Штраф за неправильный ответ
        new_score = max(
            current_score - INCORRECT_ANSWER_PENALTY * (1 + (100 - correct_percentage) / 100), 
            MIN_SCORE
        )
    
    return round(new_score, 2)

async def get_user_statistics(user_id, cursor):
    """
    Получение подробной статистики для пользователя
    """
    cursor.execute("""
        SELECT id, telegram_id, full_name, attention_score, group_id, role 
        FROM users 
        WHERE telegram_id = ?
    """, (user_id,))
    user_info = cursor.fetchone()
    
    if not user_info:
        return None
    
    cursor.execute("""
        WITH user_poll_stats AS (
            SELECT 
                p.id AS poll_id,
                p.question,
                MAX(CASE WHEN o.is_answer = 1 THEN 1 ELSE 0 END) AS correct_option_exists,
                MAX(CASE WHEN uo.option_id IS NOT NULL THEN 1 ELSE 0 END) AS user_answered,
                MAX(CASE WHEN uo.option_id IS NOT NULL AND o.is_answer = 1 THEN 1 ELSE 0 END) AS user_correct_answer
            FROM polls p
            JOIN groups g ON p.group_id = g.id
            JOIN options o ON o.poll_id = p.id
            LEFT JOIN user_options uo ON uo.option_id = o.id AND uo.user_id = ?
            WHERE g.id = ?
            GROUP BY p.id
        )
        SELECT 
            COUNT(*) as total_polls,
            COUNT(CASE WHEN user_answered = 1 THEN 1 END) as completed_polls,
            ROUND(COUNT(CASE WHEN user_answered = 1 THEN 1 END) * 100.0 / COUNT(*), 2) as completion_rate,
            ROUND(COUNT(CASE WHEN user_correct_answer = 1 THEN 1 END) * 100.0 / COUNT(CASE WHEN correct_option_exists = 1 THEN 1 END), 2) as correct_answers_rate
        FROM user_poll_stats
        WHERE correct_option_exists = 1
    """, (user_info[0], user_info[4]))
    poll_stats = cursor.fetchone()
    
    cursor.execute("""
        SELECT name FROM groups WHERE id = ?
    """, (user_info[4],))
    group_info = cursor.fetchone()
    
    return {
        "user_id": user_info[1],
        "full_name": user_info[2],
        "attention_score": user_info[3],
        "role": user_info[5],
        "group_name": group_info[0] if group_info else None,
        "total_polls": poll_stats[0],
        "completed_polls": poll_stats[1],
        "completion_rate": poll_stats[2],
        "correct_answers_rate": poll_stats[3]
    }

async def get_admin_user_statistics(cursor):
    """
    Получение полной статистики пользователей для администратора
    """
    cursor.execute("""
        WITH user_poll_stats AS (
            SELECT 
                u.id AS user_id,
                u.telegram_id,
                u.full_name,
                u.attention_score,
                u.role,
                g.name as group_name,
                p.id AS poll_id,
                MAX(CASE WHEN o.is_answer = 1 THEN 1 ELSE 0 END) AS correct_option_exists,
                MAX(CASE WHEN uo.option_id IS NOT NULL THEN 1 ELSE 0 END) AS user_answered,
                MAX(CASE WHEN uo.option_id IS NOT NULL AND o.is_answer = 1 THEN 1 ELSE 0 END) AS user_correct_answer
            FROM users u
            LEFT JOIN groups g ON u.group_id = g.id
            LEFT JOIN polls p ON p.group_id = g.id
            LEFT JOIN options o ON o.poll_id = p.id
            LEFT JOIN user_options uo ON uo.option_id = o.id AND uo.user_id = u.id
            GROUP BY u.id, p.id
        )
        SELECT 
            telegram_id,
            full_name,
            attention_score,
            role,
            group_name,
            COUNT(DISTINCT poll_id) as total_polls,
            COUNT(DISTINCT CASE WHEN user_answered = 1 THEN poll_id END) as completed_polls,
            ROUND(COUNT(DISTINCT CASE WHEN user_answered = 1 THEN poll_id END) * 100.0 / COUNT(DISTINCT poll_id), 2) as completion_rate,
            ROUND(COUNT(DISTINCT CASE WHEN user_correct_answer = 1 THEN poll_id END) * 100.0 / COUNT(DISTINCT CASE WHEN correct_option_exists = 1 THEN poll_id END), 2) as correct_answers_rate
        FROM user_poll_stats
        WHERE correct_option_exists = 1 AND role != ?
        GROUP BY telegram_id
        ORDER BY role, correct_answers_rate DESC
    """, (Roles.admin, ))
    
    users_stats = cursor.fetchall()
    
    return [
        {
            "user_id": user[0],
            "full_name": user[1],
            "attention_score": user[2],
            "role": user[3],
            "group_name": user[4],
            "total_polls": user[5],
            "completed_polls": user[6],
            "completion_rate": user[7],
            "correct_answers_rate": user[8]
        } for user in users_stats
    ]