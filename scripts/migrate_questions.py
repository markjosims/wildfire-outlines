import json
import glob
from sqlmodel import Session, create_engine, select
from src.models import Chapter, Question, SQLModel

DB_URL = "sqlite:///data/wildfire.db"
engine = create_engine(DB_URL)

def migrate():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for json_file in glob.glob("data/*.json"):
            with open(json_file, 'r') as f:
                data = json.load(f)
                for chapter_data in data:
                    chap_id = int(chapter_data['chapter'])
                    chapter = Chapter(id=chap_id, title=chapter_data['title'])
                    session.merge(chapter) # Upsert chapter
                    
                    for q_data in chapter_data['questions']:
                        # Check if question exists by text to avoid dupes
                        statement = select(Question).where(Question.question_text == q_data['question_text'])
                        if not session.exec(statement).first():
                            q = Question(chapter_id=chap_id, **q_data)
                            session.add(q)
        session.commit()