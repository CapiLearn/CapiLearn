"""Generate fictional student conversation data for demos and analytics views."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

FICTIONAL_STUDENTS = [
    ("Amara", "Quill"),
    ("Mateo", "Lark"),
    ("Priya", "Solace"),
    ("Jordan", "Vale"),
    ("Noor", "Everly"),
    ("Elias", "Rowan"),
    ("Zuri", "Bennett"),
    ("Hana", "Mercer"),
    ("Diego", "Frost"),
    ("Mei", "Hollis"),
    ("Ari", "Monroe"),
    ("Leila", "Parker"),
    ("Samir", "Dawes"),
    ("Inez", "Calloway"),
    ("Tomas", "Reed"),
    ("Nia", "Sterling"),
    ("Kiran", "Bright"),
    ("Sofia", "Wren"),
    ("Omar", "Linden"),
    ("Chloe", "Marlow"),
    ("Ravi", "Hart"),
    ("Mina", "Prescott"),
    ("Theo", "Alcott"),
    ("Fatima", "Lang"),
    ("Jun", "Ellery"),
    ("Aaliyah", "Noble"),
    ("Luca", "Winslow"),
    ("Sana", "Brooks"),
    ("Emery", "Cove"),
    ("Anika", "Finch"),
    ("Malik", "Ashby"),
    ("Camila", "North"),
    ("Yuna", "Bellamy"),
    ("Isaac", "Pryor"),
    ("Salma", "Keene"),
    ("Ren", "Whitaker"),
    ("Lina", "Madden"),
    ("Dev", "Harlow"),
    ("Maya", "Sinclair"),
    ("Jonah", "Peale"),
]

# question, category, module, difficulty, status, message count
CONVERSATION_DETAILS = [
    (
        "How do I write a Python for loop that prints each item in a list?",
        "Python basics",
        "Python Fundamentals",
        "beginner",
        "resolved",
        6,
    ),
    (
        "Why does my Python function return None when I expect a total?",
        "Python basics",
        "Python Fundamentals",
        "beginner",
        "open",
        8,
    ),
    (
        "When should I use a dictionary instead of a list in Python?",
        "Data structures",
        "Python Fundamentals",
        "beginner",
        "resolved",
        7,
    ),
    (
        "How can I handle a ValueError when converting input to an integer?",
        "Debugging",
        "Python Fundamentals",
        "intermediate",
        "resolved",
        9,
    ),
    (
        "What is the difference between a JavaScript variable declared with let and const?",
        "JavaScript basics",
        "Frontend Foundations",
        "beginner",
        "resolved",
        5,
    ),
    (
        "How do I use map to create a new array of doubled numbers in JavaScript?",
        "JavaScript basics",
        "Frontend Foundations",
        "beginner",
        "open",
        6,
    ),
    (
        "Why is my click event listener running as soon as the page loads?",
        "Debugging",
        "Frontend Foundations",
        "intermediate",
        "needs_follow_up",
        11,
    ),
    (
        "How do semantic HTML elements help organize a course project page?",
        "HTML/CSS",
        "Frontend Foundations",
        "beginner",
        "resolved",
        4,
    ),
    (
        "How can I center a card using CSS Flexbox?",
        "HTML/CSS",
        "Frontend Foundations",
        "beginner",
        "resolved",
        5,
    ),
    (
        "Why is my CSS grid column overflowing on smaller screens?",
        "HTML/CSS",
        "Frontend Foundations",
        "intermediate",
        "open",
        10,
    ),
    (
        "How do I select all courses with more than five enrolled students in SQL?",
        "SQL",
        "SQL Basics",
        "beginner",
        "resolved",
        7,
    ),
    (
        "What is the difference between INNER JOIN and LEFT JOIN?",
        "SQL",
        "SQL Basics",
        "beginner",
        "resolved",
        8,
    ),
    (
        "How can GROUP BY help me count questions per course module?",
        "SQL",
        "SQL Basics",
        "intermediate",
        "open",
        9,
    ),
    (
        "Why should I use a parameterized SQL query instead of string formatting?",
        "SQL",
        "SQL Basics",
        "intermediate",
        "resolved",
        6,
    ),
    (
        "How do I create a new Git branch for my assignment changes?",
        "Git/GitHub",
        "Git and Collaboration",
        "beginner",
        "resolved",
        4,
    ),
    (
        "What should I do when Git reports a merge conflict in my README?",
        "Git/GitHub",
        "Git and Collaboration",
        "intermediate",
        "needs_follow_up",
        12,
    ),
    (
        "How is a pull request different from pushing commits to GitHub?",
        "Git/GitHub",
        "Git and Collaboration",
        "beginner",
        "resolved",
        6,
    ),
    (
        "How can I undo my last local Git commit while keeping the changes?",
        "Git/GitHub",
        "Git and Collaboration",
        "intermediate",
        "open",
        8,
    ),
    (
        "What does an HTTP GET request do in a simple API?",
        "APIs",
        "APIs and Backend",
        "beginner",
        "resolved",
        5,
    ),
    (
        "How do I read JSON data returned from an API in Python?",
        "APIs",
        "APIs and Backend",
        "beginner",
        "open",
        8,
    ),
    (
        "When should an API return a 404 response instead of a 400 response?",
        "APIs",
        "APIs and Backend",
        "intermediate",
        "resolved",
        9,
    ),
    (
        "How can I test an API endpoint without building a full frontend?",
        "APIs",
        "APIs and Backend",
        "intermediate",
        "needs_follow_up",
        10,
    ),
    (
        "How can a stack be used to check matching parentheses?",
        "Data structures",
        "Data Structures",
        "intermediate",
        "resolved",
        12,
    ),
    (
        "What is the main difference between a queue and a stack?",
        "Data structures",
        "Data Structures",
        "beginner",
        "resolved",
        4,
    ),
    (
        "Why is looking up a key in a hash table usually fast?",
        "Data structures",
        "Data Structures",
        "intermediate",
        "open",
        11,
    ),
    (
        "How do I trace an off-by-one error in a binary search function?",
        "Debugging",
        "Data Structures",
        "intermediate",
        "needs_follow_up",
        14,
    ),
    (
        "What is the difference between training data and test data?",
        "Machine learning basics",
        "Intro to ML",
        "beginner",
        "resolved",
        6,
    ),
    (
        "Why can a model perform well on training data but poorly on new examples?",
        "Machine learning basics",
        "Intro to ML",
        "intermediate",
        "resolved",
        10,
    ),
    (
        "How do features and labels relate in a supervised learning dataset?",
        "Machine learning basics",
        "Intro to ML",
        "beginner",
        "open",
        7,
    ),
    (
        "What does a confusion matrix tell me about a classifier?",
        "Machine learning basics",
        "Intro to ML",
        "intermediate",
        "needs_follow_up",
        13,
    ),
    (
        "What does retrieval add to a generative AI course assistant?",
        "RAG / AI concepts",
        "AI Concepts",
        "beginner",
        "resolved",
        7,
    ),
    (
        "Why are text documents split into chunks before RAG retrieval?",
        "RAG / AI concepts",
        "AI Concepts",
        "intermediate",
        "resolved",
        9,
    ),
    (
        "What is an embedding in the context of semantic search?",
        "RAG / AI concepts",
        "AI Concepts",
        "beginner",
        "open",
        8,
    ),
    (
        "How can citations make a RAG answer easier to evaluate?",
        "RAG / AI concepts",
        "AI Concepts",
        "intermediate",
        "needs_follow_up",
        11,
    ),
    (
        "Why does my Python list index cause an IndexError in this loop?",
        "Debugging",
        "Python Fundamentals",
        "beginner",
        "resolved",
        6,
    ),
    (
        "How do I validate a form field with simple JavaScript before submitting?",
        "JavaScript basics",
        "Frontend Foundations",
        "intermediate",
        "open",
        10,
    ),
    (
        "How can I make an HTML image accessible with alt text?",
        "HTML/CSS",
        "Frontend Foundations",
        "beginner",
        "resolved",
        3,
    ),
    (
        "What SQL query can find modules with no associated conversations?",
        "SQL",
        "SQL Basics",
        "advanced",
        "needs_follow_up",
        15,
    ),
    (
        "How do I explain recursion using a simple factorial example?",
        "Data structures",
        "Data Structures",
        "intermediate",
        "resolved",
        8,
    ),
    (
        "How can retrieval quality be measured for a small RAG demo?",
        "RAG / AI concepts",
        "AI Concepts",
        "advanced",
        "open",
        16,
    ),
]


def build_conversation_records() -> list[dict[str, str | int]]:
    """Create deterministic fictional records for dashboard demos."""
    base_time = datetime(2026, 1, 12, 14, 0, tzinfo=UTC)
    records = []

    for index, ((first_name, last_name), details) in enumerate(
        zip(FICTIONAL_STUDENTS, CONVERSATION_DETAILS), start=1
    ):
        question, category, module, difficulty, status, message_count = details
        created_at = base_time + timedelta(days=index - 1, hours=index % 5)
        last_active_at = created_at + timedelta(hours=message_count + index % 4)
        email_name = f"{first_name}.{last_name}".lower()

        records.append(
            {
                "user_id": f"user_{index:03d}",
                "first_name": first_name,
                "last_name": last_name,
                "email": f"{email_name}@example.com",
                "conversation_id": f"conv_{index:03d}",
                "message_count": message_count,
                "sample_question": question,
                "question_category": category,
                "created_at": created_at.isoformat(),
                "user_role": "student",
                "course_module": module,
                "difficulty_level": difficulty,
                "conversation_status": status,
                "last_active_at": last_active_at.isoformat(),
            }
        )

    return records


def main() -> None:
    output_path = Path(__file__).resolve().parent / "dummy_user_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = build_conversation_records()
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(records, output_file, indent=2)
        output_file.write("\n")

    print(f"Created {len(records)} conversation records at {output_path}")


if __name__ == "__main__":
    main()
