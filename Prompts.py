"""
MyEdBase - Centralized AI Prompts & Schemas

This file contains ALL prompts and response schemas for AI interactions.
Prompts are designed to be:
- Clear and focused on learning outcomes
- Free of over-instructions
- Using structured response schemas instead of JSON in prompts
"""

# =============================================================================
# RESPONSE SCHEMAS - Used with Gemini's response_schema parameter
# =============================================================================

SCHEMAS = {
    
    # --- Topic Validation ---
    "validate_topic": {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "reason": {"type": "string"},
            "is_too_broad": {"type": "boolean"},
            "suggestions": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["valid", "is_too_broad"]
    },
    
    # --- Assessment Questions ---
    "assessment_questions": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "type": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "purpose": {"type": "string"}
                    },
                    "required": ["question", "type", "options"]
                }
            }
        },
        "required": ["questions"]
    },
    
    # --- Curriculum Generation ---
    "curriculum": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "learningStyle": {"type": "string"},
            "modules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "estimated_time": {"type": "string"},
                        "submodules": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "estimated_time": {"type": "string"}
                                },
                                "required": ["title", "description"]
                            }
                        }
                    },
                    "required": ["title", "description", "submodules"]
                }
            }
        },
        "required": ["title", "description", "modules"]
    },
    
    # --- Curriculum Modification ---
    "curriculum_modification": {
        "type": "object",
        "properties": {
            "isValidRequest": {"type": "boolean"},
            "rejectionReason": {"type": "string"},
            "message": {"type": "string"},
            "modifiedCurriculum": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "modules": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "estimated_time": {"type": "string"},
                                "submodules": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "title": {"type": "string"},
                                            "description": {"type": "string"},
                                            "estimated_time": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "required": ["isValidRequest", "message"]
    },
    
    # --- Submodule Content ---
    "submodule_content": {
        "type": "object",
        "properties": {
            "introduction": {"type": "string"},
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "comprehensionQuestion": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "string"}},
                                "correctAnswer": {"type": "string"},
                                "hint": {"type": "string"}
                            },
                            "required": ["question", "options", "correctAnswer", "hint"]
                        },
                        "flashcards": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "front": {"type": "string"},
                                    "back": {"type": "string"}
                                },
                                "required": ["front", "back"]
                            }
                        }
                    },
                    "required": ["title", "content", "comprehensionQuestion", "flashcards"]
                }
            },
            "optionalSections": {
                "type": "object",
                "properties": {
                    "realWorldApplications": {"type": "array", "items": {"type": "string"}},
                    "commonMistakes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "mistake": {"type": "string"},
                                "why": {"type": "string"},
                                "correct": {"type": "string"}
                            }
                        }
                    },
                    "proTips": {"type": "array", "items": {"type": "string"}},
                    "examples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "content": {"type": "string"},
                                "code": {"type": "string"}
                            }
                        }
                    },
                    "conclusion": {"type": "string"}
                }
            },
            "diagram": {
                "type": "object",
                "description": "Optional visual diagram to aid understanding. Only include if it genuinely helps explain the concept.",
                "properties": {
                    "title": {"type": "string", "description": "What the diagram illustrates"},
                    "description": {"type": "string", "description": "Brief explanation of what the diagram shows"},
                    "plantuml": {"type": "string", "description": "PlantUML code for the diagram"}
                },
                "required": ["title", "description", "plantuml"]
            },
            "summary": {"type": "string"}
        },
        "required": ["introduction", "topics", "summary"]
    },
    
    # --- Quiz Generation ---
    "quiz": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "questionText": {"type": "string"},
                        "type": {"type": "string"},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "correctAnswer": {"type": "string"},
                        "explanation": {"type": "string"},
                        "hint": {"type": "string"},
                        "difficulty": {"type": "string"}
                    },
                    "required": ["questionText", "options", "correctAnswer"]
                }
            }
        },
        "required": ["questions"]
    },
    
    # --- Module Exam ---
    "module_exam": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "questionText": {"type": "string"},
                        "type": {"type": "string", "enum": ["multiple-choice", "multi-select", "short-answer", "coding"]},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "correctAnswer": {"type": "string"},
                        "correctAnswers": {"type": "array", "items": {"type": "string"}},
                        "explanation": {"type": "string"},
                        "hint1": {"type": "string"},
                        "hint2": {"type": "string"},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "submoduleRef": {"type": "string"}
                    },
                    "required": ["questionText", "type", "correctAnswer", "explanation", "hint1", "hint2", "difficulty"]
                }
            }
        },
        "required": ["title", "description", "questions"]
    },
    
    # --- Chat Tutor Response ---
    "chat_response": {
        "type": "object",
        "properties": {
            "message": {"type": "string"},
            "suggestedFollowups": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["message"]
    },
    
    # --- Answer Grading ---
    "grade_answer": {
        "type": "object",
        "properties": {
            "score": {"type": "integer"},
            "feedback": {"type": "string"}
        },
        "required": ["score", "feedback"]
    },
    
    # --- Submodules Expansion ---
    "submodules": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "estimated_time": {"type": "string"}
            },
            "required": ["title", "description", "estimated_time"]
        }
    },
    
    # --- Remedial Content ---
    "remedial_content": {
        "type": "object",
        "properties": {
            "introduction": {"type": "string"},
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "practiceProblems": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "problem": {"type": "string"},
                                    "solution": {"type": "string"},
                                    "hint": {"type": "string"}
                                }
                            }
                        },
                        "flashcards": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "front": {"type": "string"},
                                    "back": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            },
            "diagram": {
                "type": "object",
                "description": "Optional visual diagram to clarify misunderstandings",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "plantuml": {"type": "string"}
                }
            },
            "summary": {"type": "string"}
        },
        "required": ["introduction", "topics", "summary"]
    },
    
    # --- Remedial Module ---
    "remedial_module": {
        "type": "object",
        "properties": {
            "moduleTitle": {"type": "string"},
            "description": {"type": "string"},
            "subModules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "practiceQuestions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string"},
                                    "answer": {"type": "string"},
                                    "explanation": {"type": "string"}
                                }
                            }
                        },
                        "diagram": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "plantuml": {"type": "string"}
                            }
                        }
                    }
                }
            }
        },
        "required": ["moduleTitle", "subModules"]
    }
}


# =============================================================================
# PROMPTS - Clean, focused prompts without JSON formatting instructions
# =============================================================================

def get_validate_topic_prompt(topic: str) -> str:
    """Validate if a topic is suitable for a course."""
    return f"""Evaluate "{topic}" as a potential online course topic.

VALIDITY CHECK (set valid=false if ANY apply):
- Contains spelling errors or typos (misspelled words that aren't recognized terms)
- Is gibberish, random characters, or keyboard patterns
- Is too vague or ambiguous to create structured content (unclear what the learner wants)
- Is offensive, harmful, or inappropriate for education
- Is a person's name, company name, or brand without educational context
- Something that takes years to learn

SCOPE CHECK (set is_too_broad=true ONLY if):
- It represents an entire academic discipline or field of study that would take years to cover
- It cannot reasonably be taught in a 5-20 hour course format

IMPORTANT: Well-known abbreviations, acronyms, and industry terms ARE VALID (they are recognized learning topics). Do not mark them as invalid just because they are short or abbreviated.

If is_too_broad=true, provide 3-4 specific suggestions that narrow down the topic.
If valid=false, provide a clear reason explaining why."""


def get_assessment_questions_prompt(topic: str) -> str:
    """Generate questions to understand learner's needs."""
    return f"""Generate personalized assessment questions to customize a course on "{topic}".

Your goal is to understand the learner well enough to create a perfectly tailored curriculum. Think about what information would genuinely help personalize their learning experience for "{topic}".

Generate questions that capture:
- Their current skill/knowledge level with {topic}
- What they want to accomplish or build with this knowledge
- Their background that might affect how they learn {topic} (relevant prior experience, related skills)
- Specific areas within {topic} they're most interested in
- How and where they plan to apply this knowledge

For technical topics, consider asking about:
- Programming languages or tools they already know
- Types of projects they want to build

For non-technical topics, consider asking about:
- Their professional or personal context
- What problems they're trying to solve

REQUIRED: Include a time investment question asking how many hours they want to spend learning {topic}. Provide realistic hour options based on what's needed to learn {topic} properly (e.g., for simple topics: 2-4 hours, for comprehensive topics: 6-15 hours, for advanced topics: 15-30 hours).

Each question should have:
- question: clear, conversational question text
- type: "single" for mutually exclusive choices, "multiple" when selecting several makes sense
- options: relevant choices (as many as make sense - don't artificially limit)

Generate as many questions as genuinely needed to understand the learner - typically 4-7 but use your judgment based on the topic's complexity."""


def get_curriculum_prompt(topic: str, qa_context: str, target_duration: int = 6) -> str:
    """Generate a personalized curriculum."""
    return f"""Design the ideal learning curriculum for "{topic}" based on this learner's profile:

{qa_context}

Think like an expert instructor who deeply understands both the subject matter and effective learning design.

CURRICULUM STRUCTURE:
Create a course organized as:
- **Modules**: Major learning milestones (chapters of the course)
- **Submodules**: Individual lessons within each module (each completable in 15-45 mins)

Each MODULE must contain 2-8 submodules. Every module needs submodules - a module without submodules is incomplete.

DESIGN PRINCIPLES:
- Start from the learner's current level
- Build concepts in logical sequence where each module unlocks understanding for the next  
- Balance theory with practical application based on their goals
- Include hands-on exercises relevant to how they'll use this knowledge

WHAT MAKES A GREAT CURRICULUM:
- Modules represent meaningful milestones in the learning journey
- Submodules are focused, single-session lessons that build toward the module's goal
- Progression feels natural and purposeful
- By completion, the learner achieves what they set out to do

REQUIRED FOR EACH ELEMENT:
- Module: title, description, estimated_time (total for module), submodules array
- Submodule: title, description, estimated_time (e.g., "30 mins", "45 mins")

Design exactly as many modules as the topic genuinely requires - let content dictate structure."""


def get_curriculum_modification_prompt(topic: str, current_curriculum: dict, user_request: str) -> str:
    """Generate modified curriculum based on user's request."""
    import json
    curriculum_json = json.dumps(current_curriculum, indent=2)
    
    return f"""You are a curriculum designer. A learner has a curriculum for "{topic}" and wants to make changes.

CURRENT CURRICULUM:
{curriculum_json}

USER'S MODIFICATION REQUEST:
"{user_request}"

YOUR TASK: Evaluate the request and modify the curriculum if appropriate.

STEP 1 - VALIDATE THE REQUEST:
Set isValidRequest=false if the request is:
- Completely unrelated to the course topic "{topic}" (e.g., asking about cooking in a programming course)
- Inappropriate, offensive, or nonsensical
- Asking to remove ALL content (must keep at least 1 module with 2+ submodules)
- Physically impossible (e.g., "make the entire course 1 minute")
- Spam, gibberish, or random characters

Set isValidRequest=true for legitimate requests like:
- Adding/removing specific modules or topics
- Reordering content
- Making the course shorter/longer
- Focusing more on certain areas
- Adding more practical examples or theory
- Changing difficulty level
- Minor topic additions within scope

STEP 2 - IF VALID, MODIFY THE CURRICULUM:
- Apply the user's requested changes thoughtfully
- Maintain logical progression and coherence
- Keep the curriculum balanced and educationally sound
- Preserve unaffected modules/submodules exactly as they are
- Estimate realistic times for any new content

STEP 3 - CRAFT A HELPFUL RESPONSE MESSAGE:
- If valid: Briefly explain what changes you made
- If invalid: Politely explain why you can't make that change and suggest alternatives

RESPONSE:
- isValidRequest: true/false
- rejectionReason: (only if invalid) why you can't process this request
- message: Your response to the user (friendly, helpful)
- modifiedCurriculum: (only if valid) the complete updated curriculum with same structure"""


def get_submodule_content_prompt(topic: str, submodule_title: str, user_level: str, context: str = "") -> str:
    """Generate rich educational content for a submodule."""
    level_guidance = {
        "beginner": "Use simple language, relatable analogies, and step-by-step explanations. Assume no prior knowledge.",
        "intermediate": "Assume foundational knowledge. Focus on practical applications, patterns, and connecting concepts.",
        "advanced": "Go deep into technical details, edge cases, best practices, and performance considerations."
    }.get(user_level.lower(), "Balance theory with practical examples at an intermediate level.")
    
    return f"""Create a comprehensive, engaging lesson on "{submodule_title}" as part of learning {topic}.

LEARNER LEVEL: {user_level}
{level_guidance}

{f"CONTEXT: {context}" if context else ""}

CRITICAL: Generate content in this EXACT JSON structure. Do NOT put content inside a "lesson" wrapper. 
The "topics" array MUST be at the root level, not nested inside anything else.

REQUIRED STRUCTURE:
{{
  "introduction": "2-3 paragraphs introducing the topic, why it matters, what they'll learn",
  "topics": [
    {{
      "title": "Clear topic heading",
      "content": "Rich markdown content with comprehensive explanations, make content engaging and easy to understand and gold standard quality, code examples, tips",
      "comprehensionQuestion": {{
        "question": "A thought-provoking MCQ question",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correctAnswer": "Option A",
        "hint": "A helpful hint without giving away the answer"
      }},
      "flashcards": [
        {{"front": "Question or concept", "back": "Answer or explanation"}}
      ]
    }}
  ],
  "optionalSections": {{
    "realWorldApplications": ["Use case 1", "Use case 2"],
    "commonMistakes": [{{"mistake": "What they do wrong", "why": "Why it's wrong", "correct": "The right way"}}],
    "proTips": ["Expert tip 1", "Expert tip 2"],
    "examples": [{{"title": "Example name", "content": "Explanation", "code": "code here"}}],
    "conclusion": "Motivating wrap-up"
  }},
  "diagram": {{
    "title": "Title describing what the diagram shows",
    "description": "Brief explanation of what this diagram illustrates and how it helps understand the concept",
    "plantuml": "@startuml\\n... PlantUML code ...\\n@enduml"
  }},
  "summary": "Concise summary of key takeaways"
}}

REQUIREMENTS:
1. Generate 3-5 topics in the topics array
2. EVERY topic MUST have a comprehensionQuestion object with question, options (4 choices), correctAnswer (exact match to one option), and hint
3. EVERY topic MUST have 2-3 flashcards with front and back
4. Content should use markdown: headers (##, ###), code blocks (```python), bullet points, **bold**
5. Make comprehension questions test UNDERSTANDING, not just recall
6. Ensure correctAnswer exactly matches one of the options

OPTIONAL DIAGRAM - Include ONLY if it genuinely helps understanding:
- Include a "diagram" field ONLY when the concept can be better understood visually
- Skip for: simple definitions, or topics that don't benefit from visualization
- The diagram should illustrate CONCEPTUAL understanding
- Use PlantUML syntax: activity diagrams, mind maps, sequence diagrams, or component diagrams or any valid plantuml diagrams


QUALITY: Make it feel like learning from an expert mentor. Be thorough but engaging."""

def get_quiz_prompt(submodule_title: str, content_summary: str, user_level: str) -> str:
    """Generate a quiz to test understanding of lesson content."""
    return f"""You are a quiz master for an educational platform. Create a knowledge test for the lesson: "{submodule_title}"

LESSON CONTENT THE LEARNER JUST STUDIED:
{content_summary[:2000] if content_summary else f"Core concepts of {submodule_title}"}

USER LEVEL: {user_level}

YOUR TASK: Generate 5-7 smart questions that TEST THE LEARNER'S KNOWLEDGE of the content above.

WHAT MAKES A GREAT QUESTION:
- Tests understanding, not just memorization
- Has real educational value - the learner thinks "that was a good question"
- Wrong options are plausible (common misconceptions, not obviously wrong)
- The explanation teaches something, not just "Option B is correct"

ABSOLUTELY AVOID:
✗ Feedback questions ("Was this helpful?", "How do you feel about...")
✗ Opinion questions ("Do you think...", "Would you prefer...")
✗ Meta-questions ("What did you learn?", "What was covered?")
✗ Trivial questions with obvious answers
✗ Questions unrelated to the lesson content

QUESTION STRUCTURE:
- **questionText**: Clear, thought-provoking question from the lesson
- **type**: "multiple_choice"
- **options**: 4 options (one correct, three plausible wrong answers)
- **correctAnswer**: Exact match to correct option
- **hint**: Helpful nudge without giving away the answer
- **explanation**: Teach WHY this is correct (2-3 sentences)
- **difficulty**: "easy", "medium", or "hard" - progress through the quiz

Create questions that a {user_level} learner would find appropriately challenging. Be creative - ask about real scenarios, edge cases, and practical applications when the content supports it."""


def get_module_exam_prompt(module_title: str, submodules: list, user_level: str) -> str:
    """Generate a comprehensive module exam."""
    submodule_list = "\n".join([f"- {s}" for s in submodules])
    
    return f"""You are an exam creator for an educational platform. Create a comprehensive MODULE EXAM for: "{module_title}"

This exam tests knowledge from ALL of these submodules:
{submodule_list}

USER LEVEL: {user_level}

YOUR TASK: Generate 8-12 questions that TEST THE LEARNER'S KNOWLEDGE of the topics covered in this module.

CRITICAL - WHAT QUESTIONS SHOULD DO:
✓ Test if the learner KNOWS and UNDERSTANDS the material from all submodules
✓ Ask about concepts, definitions, processes, or applications taught in the lessons
✓ Include integrative questions that connect concepts from different submodules
✓ Test practical application: "In this situation, what would you do?"
✓ Test deeper understanding: "Why is X preferred over Y?"

CRITICAL - WHAT TO ABSOLUTELY AVOID:
✗ DO NOT ask feedback questions like "Did you find this module useful?"
✗ DO NOT ask opinion questions like "How confident do you feel about...?"
✗ DO NOT ask meta-questions like "What was your biggest takeaway?"
✗ DO NOT ask about the learner's experience or feelings about the content
✗ This is a KNOWLEDGE EXAM, not a feedback form or survey!

QUESTION TYPES TO INCLUDE:
- 4-5 multiple-choice (single correct answer)
- 2-3 multi-select (multiple correct answers)
- 1-2 short-answer (for {user_level} level)
- 1-2 scenario-based application questions

QUESTION STRUCTURE:
- **questionText**: Clear question testing knowledge from the module
- **type**: "multiple-choice", "multi-select", or "short-answer"
- **options**: 4 options for MCQ (plausible distractors based on common misunderstandings)
- **correctAnswer/correctAnswers**: The correct answer(s)
- **hint1**: First hint (subtle nudge)
- **hint2**: Second hint (more direct guidance)
- **explanation**: Why this answer is correct, which submodule covered this
- **difficulty**: "easy", "medium", or "hard"
- **submoduleRef**: Which submodule this question relates to

Progress from easier to harder. Every question must test actual knowledge from the lessons."""


def get_chat_tutor_prompt(topic: str, content_context: str, chat_history: str, user_message: str) -> str:
    """Generate a helpful tutor response."""
    return f"""You are an expert tutor helping someone learn {topic}.

Current lesson context:
{content_context[:1000]}

Recent conversation:
{chat_history}

Student's question: {user_message}

Respond as a knowledgeable, encouraging tutor would:
- Answer their question clearly and thoroughly
- Use examples that connect to what they're learning
- If they're confused, try a different explanation approach
- Suggest follow-up questions they might find valuable"""


def get_grade_answer_prompt(question: str, correct_answer: str, student_answer: str) -> str:
    """Grade a student's written answer."""
    return f"""Grade this student answer.

Question: {question}
Expected answer: {correct_answer}
Student's answer: {student_answer}

Evaluate:
- How well does the answer demonstrate understanding?
- Are key concepts correctly explained?
- Any misconceptions that should be addressed?

Provide a score (0-100) and brief, constructive feedback."""


def get_remedial_content_prompt(submodule_title: str, weak_areas: list, user_level: str) -> str:
    """Generate remedial content for struggling learners."""
    weak_list = ", ".join(weak_areas) if weak_areas else "general concepts"
    
    return f"""A learner is struggling with "{submodule_title}", particularly: {weak_list}

Create comprehensive remedial content to help them master these concepts.

CRITICAL APPROACH - This learner didn't understand the first time, so:
- Use COMPLETELY DIFFERENT explanations and analogies than typical teaching
- Start even simpler - assume less background knowledge
- Use relatable, everyday analogies
- Break complex ideas into bite-sized, numbered steps
- Include visual thinking cues ("imagine...", "picture this...")
- Be encouraging and build confidence with each small win

REQUIRED STRUCTURE:
{{
  "introduction": "Encouraging intro acknowledging the topic can be tricky, but they'll master it with this different approach",
  "topics": [
    {{
      "title": "Concept explained differently",
      "content": "Rich markdown with step-by-step breakdown, vivid analogies, and multiple 'Aha!' moments",
      "practiceProblems": [
        {{
          "problem": "Simple problem to build confidence",
          "hint": "Helpful nudge without giving answer",
          "solution": "Complete worked solution with reasoning at each step"
        }}
      ],
      "flashcards": [
        {{"front": "Key concept question", "back": "Clear, memorable answer"}}
      ]
    }}
  ],
  "diagram": {{
    "title": "Visual representation of the concept",
    "description": "How this diagram clarifies the concept",
    "plantuml": "@startuml ... @enduml"
  }},
  "summary": "Confidence-building summary of what they've now mastered"
}}

OPTIONAL DIAGRAM - Include ONLY if visualization helps:
- Perfect for: showing relationships, processes, or comparisons
- Use simple PlantUML: activity diagrams, mindmaps, or flowcharts
- Focus on CONCEPTUAL clarity, not technical diagrams
- Make it help them "see" what they couldn't understand before

Generate 2-4 focused topics. Target {user_level} level but simpler than the original content.
Make the learner feel "Now I get it!" by the end."""


def get_remedial_module_prompt(module_title: str, failed_topics: list, wrong_answers: list) -> str:
    """Generate a remedial module for exam failures."""
    topics = "\n".join([f"- {t}" for t in failed_topics])
    mistakes = "\n".join([f"- {m}" for m in wrong_answers[:5]])
    
    return f"""Create a targeted review module for a student who failed the exam on: "{module_title}"

Topics they struggled with:
{topics}

Their actual mistakes (reveals misconceptions):
{mistakes}

YOUR MISSION: Diagnose their misunderstandings and fix them with targeted teaching.

REQUIRED STRUCTURE:
{{
  "moduleTitle": "Mastering [Topic] - A Fresh Approach",
  "description": "Brief encouraging description",
  "subModules": [
    {{
      "title": "Clear, inviting submodule title",
      "content": "Rich markdown content that:
        - DIRECTLY addresses their misconceptions
        - Uses completely different examples than original
        - Includes 'Common Trap' callouts for their specific mistakes
        - Builds understanding step-by-step
        - Uses analogies, visuals in words, and clear structure",
      "practiceQuestions": [
        {{
          "question": "Question testing the concept they got wrong",
          "answer": "Correct answer",
          "explanation": "WHY this is correct and why the common wrong answer is wrong"
        }}
      ],
      "diagram": {{
        "title": "Visual clarification",
        "description": "How this helps understanding",
        "plantuml": "@startuml ... @enduml"
      }}
    }}
  ]
}}

DIAGRAM GUIDELINES:
- Include a diagram in submodules where visualization genuinely helps
- Use PlantUML: activity diagrams (@startuml), mindmaps (@startmindmap), or simple component diagrams or any valid plantuml diagrams
- Keep diagrams SIMPLE and focused on the core concept
- Skip diagrams for purely theoretical/definition content

QUALITY REQUIREMENTS:
- Address each failed topic with its own submodule
- Reference their SPECIFIC mistakes and correct them
- Be shorter than original content - focused like a tutor session
- Make them feel capable, not stupid
- End each submodule with a confidence boost

This should feel like getting help from a patient, expert tutor who knows exactly where they went wrong."""


def get_expand_module_prompt(module_title: str, module_description: str, course_topic: str, target_level: str) -> str:
    """Generate submodules for a module."""
    return f"""Create submodules for the module "{module_title}" in a course about "{course_topic}".

Module description: {module_description}
Target level: {target_level}

Design focused submodules that:
- Break down the module into logical learning units
- Can each be completed in 15-45 minutes
- Build upon each other progressively
- Cover the module's learning objectives thoroughly"""


def get_module_exam_with_content_prompt(module_title: str, content_summaries: str, user_level: str) -> str:
    """Generate a module exam based on actual content."""
    
    return f"""You are an expert assessment designer. Create a rigorous, thought-provoking exam for module: "{module_title}"

USER LEVEL: {user_level}

CONTENT COVERED:
{content_summaries[:3000]}

EXAM DESIGN PHILOSOPHY:
- Questions should test TRUE UNDERSTANDING, not surface-level recall
- Use Bloom's Taxonomy: include Analyze, Evaluate, and Apply level questions
- Create questions that reveal whether someone truly grasps the concepts
- Include scenarios that require connecting multiple concepts
- Avoid questions with obvious wrong answers - make distractors plausible

Generate the exam in this EXACT JSON structure:
{{
  "title": "Module Exam: {module_title}",
  "description": "Demonstrate your mastery of {module_title} through this comprehensive assessment.",
  "questions": [
    {{
      "questionText": "A precise, well-crafted question that tests understanding",
      "type": "multiple-choice",
      "options": ["Plausible option A", "Plausible option B", "Plausible option C", "Plausible option D"],
      "correctAnswer": "The correct option",
      "explanation": "Clear explanation of why this is correct AND why each distractor is wrong",
      "hint1": "Guides thinking without revealing - connects to a relevant concept",
      "hint2": "More direct guidance - narrows down the reasoning path",
      "difficulty": "easy",
      "submoduleRef": "Related submodule title"
    }},
    {{
      "questionText": "Select ALL correct statements about...",
      "type": "multi-select",
      "options": ["Statement A", "Statement B", "Statement C", "Statement D"],
      "correctAnswer": "Statement A, Statement C",
      "correctAnswers": ["Statement A", "Statement C"],
      "explanation": "Why each correct answer is right and incorrect ones are wrong",
      "hint1": "Consider the key principles from...",
      "hint2": "Remember that X applies to...",
      "difficulty": "medium",
      "submoduleRef": "Related submodule"
    }},
    {{
      "questionText": "Given this scenario, explain how you would...",
      "type": "short-answer",
      "options": [],
      "correctAnswer": "Key concepts and reasoning the answer must demonstrate",
      "explanation": "Complete model answer with full reasoning",
      "hint1": "Start by considering...",
      "hint2": "The key factor here is...",
      "difficulty": "hard",
      "submoduleRef": "Related submodule"
    }}
  ]
}}

QUESTION QUALITY REQUIREMENTS:
1. Generate 8-12 questions total
2. EVERY question MUST have: questionText, type, correctAnswer, explanation, hint1, hint2, difficulty
3. Question type distribution:
   - 4-6 multiple-choice (each with 4 plausible options)
   - 1-2 multi-select (test comprehensive understanding)
   - 1-2 short-answer (test ability to explain/apply)
   - IF the content involves programming, coding, or technical skills: include 1-2 coding questions (type: "coding", options: [], correctAnswer: expected code/approach)

COGNITIVE DEPTH REQUIREMENTS:
4. Include at least 2 "Why" questions (test understanding of reasoning)
5. Include at least 2 "What if" questions (test ability to apply in new contexts)
6. Include at least 1 question connecting concepts across different submodules
7. Avoid pure definition/recall questions - always add application context

DIFFICULTY CALIBRATION:
8. Easy (2-3): Direct application of single concept
9. Medium (3-4): Requires combining 2+ concepts or analyzing scenarios
10. Hard (2-3): Complex scenarios, edge cases, or synthesis of multiple ideas

HINT GUIDELINES:
11. hint1: Subtle nudge toward the right thinking framework (costs -10%)
12. hint2: More specific guidance without giving away the answer (costs -10%)

IMPORTANT: Analyze the content above to determine if this is a programming/technical topic. If it involves code, algorithms, or technical implementation, include coding questions. Otherwise, focus on conceptual and application questions.

Create an exam that a {user_level} level learner would find appropriately challenging but fair."""
