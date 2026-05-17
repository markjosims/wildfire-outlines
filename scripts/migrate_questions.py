import json
import glob
from sqlmodel import Session, select
from src.models import Chapter, Question
from src.assessment_server import AssessmentServer

JSON_FILE = "data/wildfire_questions_B.json"


def migrate():
    server = AssessmentServer()
    server.init_db()

    with Session(server.engine) as session:
        with open(JSON_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping {JSON_FILE}: Invalid JSON")
                return

            for chapter_data in data:
                chap_id = int(chapter_data["chapter"])
                chapter = Chapter(id=chap_id, title=chapter_data["title"])
                session.merge(chapter)  # Upsert chapter

                for question_data in chapter_data["questions"]:
                    # Check if question exists by text to avoid dupes
                    statement = select(Question).where(
                        Question.question_text == question_data["question_text"]
                    )
                    if not session.exec(statement).first():
                        # Extract common fields

                        q = Question(chapter_id=chap_id, **question_data)
                        session.add(q)
        session.commit()


if __name__ == "__main__":
    migrate()
