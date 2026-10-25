import os, sys
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, MetaData, Table, Column, Integer, String, Text, Boolean, TIMESTAMP, ForeignKey
from alembic import context

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('SCHEDULE_PASSWORD', 'dev')

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

meta = MetaData()

schedule_days = Table(
    'schedule_days', meta,
    Column('id', Integer, primary_key=True),
    Column('day_name', String, nullable=False),
    Column('date', String, nullable=False),
    Column('sort_order', Integer, nullable=False, server_default='0'),
    Column('group_name', String, server_default=''),
    Column('created_at', TIMESTAMP, server_default='CURRENT_TIMESTAMP'),
    Column('deleted_at', TIMESTAMP, nullable=True),
    Column('is_published', Integer, server_default='0', nullable=False),
)

lessons = Table(
    'lessons', meta,
    Column('id', Integer, primary_key=True),
    Column('day_id', Integer, ForeignKey('schedule_days.id'), nullable=False),
    Column('period', Integer, nullable=False),
    Column('subject_id', Integer, ForeignKey('subjects.id'), nullable=True),
    Column('teacher_id', Integer, ForeignKey('teachers.id'), nullable=True),
    Column('classroom_id', Integer, ForeignKey('classrooms_list.id'), nullable=True),
    Column('group_id', Integer, ForeignKey('groups_list.id'), nullable=True),
    Column('subgroup', Integer, nullable=True),
    Column('is_substitution', Boolean, server_default='0'),
    Column('original_teacher_id', Integer, ForeignKey('teachers.id'), nullable=True),
    Column('substitution_reason', Text, nullable=True),
    Column('created_at', TIMESTAMP, server_default='CURRENT_TIMESTAMP'),
    Column('deleted_at', TIMESTAMP, nullable=True),
)

subjects = Table(
    'subjects', meta,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False, unique=True),
    Column('default_teacher_id', Integer, ForeignKey('teachers.id'), nullable=True),
)

teachers = Table(
    'teachers', meta,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
)

groups_list = Table(
    'groups_list', meta,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('course', Integer, server_default='1'),
    Column('is_distance', Integer, server_default='0'),
    Column('specialty_id', Integer, ForeignKey('specialties.id'), nullable=True),
)

specialties = Table(
    'specialties', meta,
    Column('id', Integer, primary_key=True),
    Column('code', String, nullable=False),
    Column('name', String, nullable=False),
    Column('qualification', String, nullable=True),
    Column('created_at', TIMESTAMP, server_default='CURRENT_TIMESTAMP'),
    Column('deleted_at', TIMESTAMP, nullable=True),
)

classrooms_list = Table(
    'classrooms_list', meta,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
)

excluded_dates = Table(
    'excluded_dates', meta,
    Column('id', Integer, primary_key=True),
    Column('start_date', String, nullable=False),
    Column('end_date', String, nullable=False),
    Column('reason', String, nullable=True),
    Column('created_at', TIMESTAMP, server_default='CURRENT_TIMESTAMP'),
)

lesson_history = Table(
    'lesson_history', meta,
    Column('id', Integer, primary_key=True),
    Column('lesson_id', Integer, ForeignKey('lessons.id'), nullable=False),
    Column('changed_at', TIMESTAMP, server_default='CURRENT_TIMESTAMP'),
    Column('old_subject_id', Integer, nullable=True),
    Column('old_teacher_id', Integer, nullable=True),
    Column('old_classroom_id', Integer, nullable=True),
    Column('old_group_id', Integer, nullable=True),
    Column('old_subgroup', Integer, nullable=True),
)

target_metadata = meta


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    cfg = config.get_section(config.config_ini_section, {})
    db_url = cfg.get('sqlalchemy.url')
    if not db_url or db_url == 'driver://user:pass@localhost/dbname':
        import config as app_config
        db_url = f"sqlite:///{os.path.join(app_config.DB_DIR, app_config.DB_NAME).replace(os.sep, '/')}"
    cfg['sqlalchemy.url'] = db_url
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
