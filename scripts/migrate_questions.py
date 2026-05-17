import json
import glob
from sqlmodel import Session, select
from src.models import Chapter, Question
from src.assessment_server import AssessmentServer


def migrate():
    server = AssessmentServer()
    server.init_db()

    with Session(server.engine) as session:
        for json_file in glob.glob("data/*.json"):
            with open(json_file, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    print(f"Skipping {json_file}: Invalid JSON")
                    continue

                for chapter_data in data:
                    chap_id = int(chapter_data["chapter"])
                    chapter = Chapter(id=chap_id, title=chapter_data["title"])
                    session.merge(chapter)  # Upsert chapter

                    for q_data in chapter_data["questions"]:
                        # Check if question exists by text to avoid dupes
                        statement = select(Question).where(
                            Question.question_text == q_data["question_text"]
                        )
                        if not session.exec(statement).first():
                            # Extract common fields
                            final_q_data = {
                                "concept_description": q_data.get(
                                    "concept_description", ""
                                ),
                                "question_text": q_data.get("question_text", ""),
                                "answer": q_data.get("answer", ""),
                            }

                            # Handle explanation_text (Required by model)
                            # Use explicit explanation if it exists, otherwise fallback to answer
                            explanation = q_data.get("explanation_text") or q_data.get(
                                "explanation"
                            )
                            if not explanation:
                                explanation = final_q_data["answer"]

                            final_q_data["explanation_text"] = explanation

                            q = Question(chapter_id=chap_id, **final_q_data)
                            session.add(q)
        session.commit()


if __name__ == "__main__":
    migrate()
