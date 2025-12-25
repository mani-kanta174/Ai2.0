from flask import Blueprint, request, jsonify, current_app, send_file
from ai_service import AIService
from pymongo import MongoClient
from bson.objectid import ObjectId
import jwt
import json
from datetime import datetime
from fpdf import FPDF
import io
import re
import base64
from plantweb.render import render
from gamification import (
    get_or_create_user_stats, update_streak, award_xp, 
    increment_stat, check_and_award_badges
)
from admin import log_activity
import prompts


learning_bp = Blueprint('learning', __name__)

# Helper: Get DB
def get_db():
    client = MongoClient(current_app.config['MONGO_URI'])
    return client.get_database()

# DEV ONLY: Reset all learning data
@learning_bp.route('/dev/reset-all', methods=['DELETE'])
def reset_all_data():
    """DEV ONLY: Delete ALL data from database for testing."""
    db = get_db()
    
    # Delete ALL collections
    collections_to_clear = [
        'users',
        'otps',
        'user_courses',
        'submodule_contents', 
        'submodule_tests',
        'progress_tracking',
        'module_progress',
        'user_personas',
        'user_stats',
        'chats',
        'activity_logs',
        'notes'
    ]

    
    deleted_counts = {}
    for collection in collections_to_clear:
        result = db[collection].delete_many({})
        deleted_counts[collection] = result.deleted_count
    
    return jsonify({
        'message': 'All data cleared (including users)',
        'deletedCounts': deleted_counts
    })


# PlantUML render endpoint
@learning_bp.route('/render-plantuml', methods=['POST', 'OPTIONS'])
def render_plantuml():
    """Render PlantUML code to SVG using plantweb."""
    import traceback
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        plantuml_code = data.get('code', '')
        
        if not plantuml_code:
            return jsonify({'error': 'No PlantUML code provided'}), 400
        
        print(f"[PlantUML] Rendering code of length {len(plantuml_code)}")
        
        # Clean up the PlantUML code
        plantuml_code = plantuml_code.strip()
        
        # Remove any markdown code fence artifacts
        if plantuml_code.startswith('```'):
            lines = plantuml_code.split('\n')
            # Remove first line if it's a code fence
            if lines[0].startswith('```'):
                lines = lines[1:]
            # Remove last line if it's a code fence
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            plantuml_code = '\n'.join(lines).strip()
        
        # Ensure proper PlantUML structure
        if not plantuml_code.startswith('@start'):
            plantuml_code = f"@startuml\n{plantuml_code}\n@enduml"
        
        # Validate minimum content
        if len(plantuml_code.strip()) < 20:
            print(f"[PlantUML] Code too short, skipping render")
            return jsonify({'error': 'PlantUML code too short'}), 400
        
        # Render using plantweb (uses public PlantUML server)
        # render() returns a tuple (output_bytes, format_used)
        result = render(plantuml_code, engine='plantuml', format='svg')
        
        # Handle both tuple and bytes return types
        if isinstance(result, tuple):
            svg_bytes = result[0]
        else:
            svg_bytes = result
        
        print(f"[PlantUML] Successfully rendered, SVG size: {len(svg_bytes)} bytes")
        
        # Return as base64 encoded SVG
        svg_base64 = base64.b64encode(svg_bytes).decode('utf-8')
        
        return jsonify({
            'svg': svg_base64,
            'contentType': 'image/svg+xml'
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"[PlantUML] Render error: {error_msg}")
        print(f"[PlantUML] Traceback: {traceback.format_exc()}")
        
        # Return a fallback error SVG instead of 500
        error_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100" viewBox="0 0 400 100">
            <rect width="400" height="100" fill="#fef2f2" stroke="#fca5a5" stroke-width="2" rx="8"/>
            <text x="200" y="40" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#dc2626">⚠️ Diagram render failed</text>
            <text x="200" y="65" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#991b1b">PlantUML syntax error</text>
        </svg>'''
        svg_base64 = base64.b64encode(error_svg.encode()).decode('utf-8')
        return jsonify({
            'svg': svg_base64,
            'contentType': 'image/svg+xml',
            'error': 'Render failed - showing placeholder'
        })


# Helper: Get user from token
def get_user_from_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload.get('user_id')
    except:
        return None

# Helper: Create default persona
def create_default_persona(user_id, topic):
    # Determine which domain this topic belongs to
    detected_domain = detect_domain(topic)
    
    return {
        'userId': ObjectId(user_id),
        'version': 1,
        'isActive': True,
        
        # Domain Expertise - tracks XP and progress per knowledge area
        'domainExpertise': [{
            'domain': detected_domain['domain'],
            'subdomain': detected_domain['subdomain'],
            'xp': 0,
            'level': 1,
            'coursesCompleted': 0,
            'coursesInProgress': 1,
            'totalTimeSpent': 0,
            'avgScore': 0,
            'lastActivity': datetime.utcnow()
        }],
        
        # Cognitive Profile - How they learn best (affects content generation)
        'cognitiveProfile': {
            'learningPace': 'moderate',       # slow, moderate, fast - affects content density
            'depthPreference': 'balanced',    # surface, balanced, deep - affects explanation detail
            'exampleStyle': 'practical',      # practical, theoretical, code-heavy - affects example types
            'retentionStrength': 'visual',    # visual, written, hands-on - affects content format
            'abstractThinking': 0.5,          # 0-1 - theory vs concrete examples ratio
            'preferredContentLength': 'medium' # short, medium, long - submodule content length
        },
        
        # Behavioral Traits - Study habits (affects course recommendations)
        'behavioralTraits': {
            'sessionLength': 30,              # preferred minutes per session
            'studyConsistency': 'regular',    # sporadic, regular, daily
            'challengePreference': 'balanced', # easy-first, balanced, challenge-seeker
            'completionStyle': 'sequential',  # sequential, skip-around, completionist
            'breakFrequency': 'moderate',     # rare, moderate, frequent
            'streakDays': 0,
            'longestStreak': 0
        },
        
        # Interaction Preferences - UI/UX preferences
        'interactionPreferences': {
            'quizStyle': 'mix',               # mcq, short-answer, mix
            'feedbackTiming': 'immediate',    # immediate, end-of-quiz
            'explanationDepth': 'detailed',   # brief, detailed
            'codeStyle': 'annotated',         # commented, minimal, annotated (for tech content)
            'hintsEnabled': True,
            'flashcardMode': 'spaced'         # random, spaced, sequential
        },
        
        # Topic Proficiency - specific to courses
        'topicProficiency': [{
            'topicId': str(ObjectId()),
            'topicName': topic,
            'domain': detected_domain['domain'],
            'subdomain': detected_domain['subdomain'],
            'proficiencyScore': 0.0,
            'learningLevel': 'beginner',
            'coursesCompleted': 0,
            'totalTimeSpent': 0,
            'avgTestScore': 0,
            'lastStudiedAt': None,
            'performanceTrend': 'neutral'
        }],
        
        # Adaptive Learning Signals
        'adaptiveSignals': {
            'topicsNeedingReview': [],
            'strongTopics': [],
            'suggestedNextTopics': [],
            'commonMistakes': []
        },
        
        # Update tracking
        'lastUpdateTrigger': {
            'eventType': 'persona_created',
            'eventId': None,
            'topicsAffected': [topic],
            'timestamp': datetime.utcnow()
        },
        
        'confidenceScore': 0.0,
        'dataPoints': 0,
        'createdAt': datetime.utcnow(),
        'updatedAt': datetime.utcnow()
    }


# Knowledge Domains with subdomains
KNOWLEDGE_DOMAINS = {
    "Technology": ["Programming", "Web Development", "DevOps", "Data Science", "AI/ML", "Cybersecurity", "Mobile Development", "Cloud Computing", "Databases", "Software Engineering"],
    "Business": ["Finance", "Marketing", "Entrepreneurship", "Management", "Accounting", "Economics", "Investment", "E-commerce", "Sales", "Project Management"],
    "Science": ["Physics", "Chemistry", "Biology", "Mathematics", "Astronomy", "Environmental Science", "Statistics", "Geology", "Neuroscience"],
    "Healthcare": ["Medicine", "Nursing", "Pharmacy", "Anatomy", "Nutrition", "Mental Health", "Public Health", "First Aid", "Medical Research"],
    "Creative": ["Design", "Photography", "Music", "Writing", "Film", "Animation", "Art", "UX/UI", "Content Creation"],
    "Languages": ["English", "Spanish", "French", "German", "Mandarin", "Japanese", "Korean", "Arabic", "Portuguese"],
    "Personal Development": ["Productivity", "Communication", "Leadership", "Time Management", "Public Speaking", "Mindfulness", "Career Development"]
}


def detect_domain(topic: str) -> dict:
    """Detect which domain a topic belongs to using keyword matching."""
    topic_lower = topic.lower()
    
    # Domain keywords mapping
    domain_keywords = {
        "Technology": ["python", "javascript", "programming", "code", "software", "web", "app", "database", "api", "cloud", "devops", "react", "node", "machine learning", "ai", "data science", "cyber", "security", "docker", "kubernetes"],
        "Business": ["marketing", "finance", "business", "startup", "entrepreneur", "investment", "stock", "accounting", "management", "sales", "ecommerce", "strategy"],
        "Science": ["physics", "chemistry", "biology", "math", "calculus", "statistics", "science", "experiment", "research", "astronomy", "geology"],
        "Healthcare": ["medicine", "health", "medical", "nursing", "anatomy", "pharmacy", "nutrition", "mental health", "therapy", "diagnosis"],
        "Creative": ["design", "art", "music", "photo", "video", "film", "animation", "writing", "creative", "drawing", "illustration"],
        "Languages": ["english", "spanish", "french", "german", "chinese", "japanese", "korean", "language", "grammar", "vocabulary"],
        "Personal Development": ["productivity", "leadership", "communication", "time management", "habit", "mindfulness", "career", "interview", "public speaking"]
    }
    
    for domain, keywords in domain_keywords.items():
        for keyword in keywords:
            if keyword in topic_lower:
                # Find most relevant subdomain
                subdomains = KNOWLEDGE_DOMAINS[domain]
                for sub in subdomains:
                    if sub.lower() in topic_lower or topic_lower in sub.lower():
                        return {"domain": domain, "subdomain": sub}
                return {"domain": domain, "subdomain": subdomains[0]}
    
    # Default to Technology/General if no match
    return {"domain": "Technology", "subdomain": "Programming"}

@learning_bp.route('/analyze-topic', methods=['POST'])
def analyze_topic():
    try:
        data = request.json
        topic = data.get('topic')
        if not topic:
            return jsonify({'error': 'Topic is required'}), 400
        
        # Basic sanitization
        topic = topic.strip()
        if len(topic) < 2:
            return jsonify({'error': 'Please enter a valid topic'}), 400
        if len(topic) > 200:
            return jsonify({'error': 'Topic is too long. Please be more specific.'}), 400

        # Pre-AI basic filtering for obvious gibberish
        # Check for repeated characters (like "aaaa" or "1111")
        if len(set(topic.lower().replace(' ', ''))) <= 2 and len(topic) > 3:
            return jsonify({
                'error': 'Please enter a valid learning topic.',
                'invalid_topic': True
            }), 400
        
        # Check for mostly non-alphabetic characters
        alpha_chars = sum(1 for c in topic if c.isalpha())
        if len(topic) > 3 and alpha_chars / len(topic) < 0.5:
            return jsonify({
                'error': 'Please enter a valid learning topic with actual words.',
                'invalid_topic': True
            }), 400
        
        # Check for keyboard smash patterns
        keyboard_patterns = ['qwerty', 'asdf', 'zxcv', 'qazwsx', 'poiuy', 'lkjh']
        topic_lower = topic.lower().replace(' ', '')
        if any(pattern in topic_lower for pattern in keyboard_patterns) and len(topic) < 15:
            return jsonify({
                'error': 'Please enter a real learning topic.',
                'invalid_topic': True
            }), 400

        # Step 1: Validate the topic using AI with structured output
        validation_prompt = prompts.get_validate_topic_prompt(topic)
        
        try:
            validation = AIService.generate_with_schema(
                validation_prompt, 
                prompts.SCHEMAS["validate_topic"]
            )
        except Exception as e:
            print(f"Validation error: {e}")
            validation = {"valid": True, "is_too_broad": False}
        
        # Handle invalid topic
        if not validation.get('valid', True):
            reason = validation.get('reason', 'This does not appear to be a learnable topic.')
            return jsonify({
                'error': reason,
                'invalid_topic': True
            }), 400
        
        # Handle too broad topic
        if validation.get('is_too_broad', False):
            suggestions = validation.get('suggestions', [])
            return jsonify({
                'error': 'This topic is quite broad. Consider a more specific area to learn.',
                'too_broad': True,
                'suggestions': suggestions
            }), 400

        # Step 2: Generate assessment questions for valid topics
        prompt = prompts.get_assessment_questions_prompt(topic)
        
        try:
            result = AIService.generate_with_schema(
                prompt,
                prompts.SCHEMAS["assessment_questions"]
            )
            questions = result.get('questions', [])
        except Exception as e:
            print(f"Assessment questions error: {e}")
            # Fallback to default questions
            questions = [
                {"question": f"What's your current experience with {topic}?", "type": "single", 
                 "options": ["Complete beginner", "Some basic knowledge", "Intermediate", "Advanced"]},
                {"question": "What do you want to achieve?", "type": "single",
                 "options": ["Learn fundamentals", "Build projects", "Career advancement", "Personal interest"]}
            ]
        
        return jsonify({'questions': questions})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@learning_bp.route('/generate-curriculum', methods=['POST'])
def generate_curriculum():
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
            
        data = request.json
        topic = data.get('topic')
        answers = data.get('answers') # List of {question, answer}
        
        if not topic or not answers:
            return jsonify({'error': 'Topic and answers are required'}), 400

        qa_context = "\n".join([f"Q: {item['question']}\nA: {item['answer']}" for item in answers])
        
        # Extract target duration if provided
        target_duration = data.get('targetDuration', 6)  # Default 6 hours
        
        # Add additional notes if provided
        additional_notes = data.get('additionalNotes', '').strip()
        if additional_notes:
            qa_context += f"\n\nAdditional notes from learner:\n{additional_notes}"
        
        # Generate curriculum using clean prompt
        prompt = prompts.get_curriculum_prompt(topic, qa_context, target_duration)
        
        try:
            curriculum = AIService.generate_with_schema(
                prompt,
                prompts.SCHEMAS["curriculum"]
            )
            # Handle nested curriculum structure (AI sometimes returns {curriculum: {modules: [...]}})
            if 'curriculum' in curriculum and 'modules' in curriculum.get('curriculum', {}):
                curriculum = curriculum['curriculum']
            print(f"[Curriculum] Generated: {len(curriculum.get('modules', []))} modules")
            print(f"[Curriculum] Keys: {curriculum.keys() if curriculum else 'None'}")
        except Exception as e:
            print(f"Curriculum generation error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': 'Failed to generate curriculum'}), 500
        
        # Save course to database
        db = get_db()
        
        # Build modules for DB
        db_modules = []
        modules_from_curriculum = curriculum.get('modules', [])
        print(f"[Curriculum] Processing {len(modules_from_curriculum)} modules")
        
        for i, mod in enumerate(modules_from_curriculum):
            module_id = ObjectId()
            submodules = []
            
            # Try both 'submodules' (AI response) and 'subModules' (possible alternate format)
            submodules_from_ai = mod.get('submodules', []) or mod.get('subModules', [])
            print(f"[Module {i+1}] '{mod.get('title', 'No title')}' has {len(submodules_from_ai)} submodules")
            
            # Process submodules for all modules
            for j, sub in enumerate(submodules_from_ai):
                is_first_submodule_of_first_module = (i == 0 and j == 0)
                submodules.append({
                    'subModuleId': ObjectId(),
                    'title': sub.get('title', ''),
                    'description': '',
                    'order': j + 1,
                    'estimatedDuration': parse_duration(sub.get('estimated_time', '30 mins')),
                    'isLocked': not is_first_submodule_of_first_module,
                    'unlockedAt': datetime.utcnow() if is_first_submodule_of_first_module else None,
                    'hasTest': False,
                    'contentStatus': 'pending',  # pending | generating | ready | failed
                    'quizStatus': 'pending',     # pending | generating | ready | failed
                    'contentGeneratedAt': None,
                    'quizGeneratedAt': None
                })
            
            db_modules.append({
                'moduleId': module_id,
                'title': mod.get('title', ''),
                'description': mod.get('description', ''),
                'order': i + 1,
                'difficulty': 'beginner' if i < 2 else ('intermediate' if i < 5 else 'advanced'),
                'estimatedDuration': parse_duration(mod.get('estimated_time', '2 hours')),
                'isRemedial': False,
                'isAdvanced': False,
                'parentModuleId': None,
                'prerequisites': [],
                'moduleContent': '',
                'isLocked': i > 0,
                'unlockedAt': datetime.utcnow() if i == 0 else None,
                'subModules': submodules,
                'needsGeneration': False,  # All submodules are generated upfront
                'hasTest': True,
                'testId': None,
                'examStatus': 'pending',     # pending | generating | ready | failed
                'examGeneratedAt': None
            })
        
        # Determine target level from answers
        target_level = 'beginner'
        for ans in answers:
            answer_lower = ans.get('answer', '').lower()
            if 'advanced' in answer_lower:
                target_level = 'advanced'
                break
            elif 'intermediate' in answer_lower:
                target_level = 'intermediate'
        
        course_doc = {
            'userId': ObjectId(user_id),
            'isFromPublicCatalog': False,
            'publicCourseId': None,
            'title': curriculum.get('title', topic),
            'description': curriculum.get('description', ''),
            'topic': topic,
            'targetLevel': target_level,
            'courseContext': '',
            'modules': db_modules,
            'status': 'not_started',
            'currentModuleId': db_modules[0]['moduleId'] if db_modules else None,
            'currentSubModuleId': db_modules[0]['subModules'][0]['subModuleId'] if db_modules and db_modules[0]['subModules'] else None,
            'completionPercentage': 0,
            'totalTimeSpent': 0,
            'generationParams': {
                'personaSnapshot': {
                    'version': 1,
                    'topicLevel': target_level,
                    'preferences': {},
                    'knowledgeGaps': []
                },
                'personalizationAnswers': answers,  # Store Q&A for content generation
                'learningStyle': curriculum.get('learningStyle', 'balanced'),
                'targetDuration': target_duration,
                'aiModel': current_app.config.get('AI_PROVIDER', 'gemini'),
                'generatedAt': datetime.utcnow(),
                'customPreferences': {}
            },
            'createdAt': datetime.utcnow(),
            'lastAccessedAt': datetime.utcnow(),
            'completedAt': None
        }
        
        result = db.user_courses.insert_one(course_doc)
        course_id = result.inserted_id
        
        # Create or update persona
        existing_persona = db.user_personas.find_one({'userId': ObjectId(user_id), 'isActive': True})
        if not existing_persona:
            persona = create_default_persona(user_id, topic)
            persona['lastUpdateTrigger']['eventId'] = course_id
            db.user_personas.insert_one(persona)
        else:
            # Update existing persona with new topic if not already present
            topic_exists = any(tp['topicName'] == topic for tp in existing_persona.get('topicProficiency', []))
            if not topic_exists:
                new_topic_proficiency = {
                    'topicId': str(ObjectId()),
                    'topicName': topic,
                    'learningLevel': target_level,
                    'proficiencyScore': 0.0,
                    'subTopics': [],
                    'learningPace': 'moderate',
                    'coursesCompleted': 0,
                    'totalTimeSpent': 0,
                    'performanceTrend': 'neutral',
                    'avgTestScore': 0,
                    'lastStudiedAt': None,
                    'lastTestScore': 0,
                    'topicConfidence': 0.0
                }
                db.user_personas.update_one(
                    {'_id': existing_persona['_id']},
                    {
                        '$push': {'topicProficiency': new_topic_proficiency},
                        '$set': {
                            'updatedAt': datetime.utcnow(),
                            'lastUpdateTrigger': {
                                'eventType': 'course_created',
                                'eventId': course_id,
                                'topicsAffected': [topic],
                                'timestamp': datetime.utcnow()
                            }
                        },
                        '$inc': {'dataPoints': 1}
                    }
                )
        
        # Trigger background content generation for all modules
        from background_tasks import trigger_course_content_generation
        trigger_course_content_generation(
            current_app._get_current_object(),
            str(course_id),
            user_id,
            db_modules
        )
        
        # Log activity
        log_activity(user_id, 'course_created', {
            'topic': topic,
            'title': curriculum.get('title', ''),
            'moduleCount': len(db_modules)
        }, course_id=str(course_id))
        
        return jsonify({'curriculum': curriculum, 'courseId': str(course_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@learning_bp.route('/modify-curriculum', methods=['POST'])
def modify_curriculum():
    """Modify an existing curriculum based on user's request."""
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        data = request.json
        course_id = data.get('courseId')
        user_request = data.get('request', '').strip()
        
        if not course_id or not user_request:
            return jsonify({'error': 'Course ID and modification request are required'}), 400
        
        if len(user_request) < 3:
            return jsonify({
                'success': False,
                'message': 'Please provide a more detailed request for what you\'d like to change.'
            })
        
        if len(user_request) > 500:
            return jsonify({
                'success': False,
                'message': 'Your request is too long. Please keep it under 500 characters.'
            })
        
        db = get_db()
        
        # Get the existing course
        course = db.user_courses.find_one({'_id': ObjectId(course_id), 'userId': ObjectId(user_id)})
        if not course:
            return jsonify({'error': 'Course not found'}), 404
        
        # Build current curriculum structure for the prompt
        current_curriculum = {
            'title': course.get('title', ''),
            'description': course.get('description', ''),
            'modules': []
        }
        
        for mod in course.get('modules', []):
            module_data = {
                'title': mod.get('title', ''),
                'description': mod.get('description', ''),
                'estimated_time': f"{mod.get('estimatedDuration', 60)} mins",
                'submodules': []
            }
            for sub in mod.get('subModules', []):
                module_data['submodules'].append({
                    'title': sub.get('title', ''),
                    'description': sub.get('description', ''),
                    'estimated_time': f"{sub.get('estimatedDuration', 30)} mins"
                })
            current_curriculum['modules'].append(module_data)
        
        topic = course.get('topic', '')
        
        # Generate modification using AI
        prompt = prompts.get_curriculum_modification_prompt(topic, current_curriculum, user_request)
        
        try:
            result = AIService.generate_with_schema(prompt, prompts.SCHEMAS["curriculum_modification"])
        except Exception as e:
            print(f"Curriculum modification error: {e}")
            return jsonify({
                'success': False,
                'message': 'Sorry, I couldn\'t process your request. Please try again with different wording.'
            })
        
        # Check if request was valid
        if not result.get('isValidRequest', False):
            return jsonify({
                'success': False,
                'message': result.get('message', 'Sorry, I couldn\'t apply that change to your curriculum.')
            })
        
        # Get the modified curriculum
        modified = result.get('modifiedCurriculum')
        if not modified or not modified.get('modules'):
            return jsonify({
                'success': False,
                'message': 'The modification couldn\'t be applied. Please try a different request.'
            })
        
        # Rebuild the modules for the database
        new_modules = []
        for i, mod in enumerate(modified.get('modules', [])):
            module_id = ObjectId()
            submodules = []
            
            for j, sub in enumerate(mod.get('submodules', [])):
                is_first = (i == 0 and j == 0)
                submodules.append({
                    'subModuleId': ObjectId(),
                    'title': sub.get('title', ''),
                    'description': sub.get('description', ''),
                    'order': j + 1,
                    'estimatedDuration': parse_duration(sub.get('estimated_time', '30 mins')),
                    'isLocked': not is_first,
                    'unlockedAt': datetime.utcnow() if is_first else None,
                    'hasTest': False,
                    'contentStatus': 'pending',
                    'quizStatus': 'pending',
                    'contentGeneratedAt': None,
                    'quizGeneratedAt': None
                })
            
            new_modules.append({
                'moduleId': module_id,
                'title': mod.get('title', ''),
                'description': mod.get('description', ''),
                'order': i + 1,
                'difficulty': 'beginner' if i < 2 else ('intermediate' if i < 5 else 'advanced'),
                'estimatedDuration': parse_duration(mod.get('estimated_time', '2 hours')),
                'isRemedial': False,
                'isAdvanced': False,
                'parentModuleId': None,
                'prerequisites': [],
                'moduleContent': '',
                'isLocked': i > 0,
                'unlockedAt': datetime.utcnow() if i == 0 else None,
                'subModules': submodules,
                'needsGeneration': False,
                'hasTest': True,
                'testId': None,
                'examStatus': 'pending',
                'examGeneratedAt': None
            })
        
        # Update the course in database
        db.user_courses.update_one(
            {'_id': ObjectId(course_id)},
            {
                '$set': {
                    'title': modified.get('title', course.get('title')),
                    'description': modified.get('description', course.get('description')),
                    'modules': new_modules,
                    'currentModuleId': new_modules[0]['moduleId'] if new_modules else None,
                    'currentSubModuleId': new_modules[0]['subModules'][0]['subModuleId'] if new_modules and new_modules[0]['subModules'] else None,
                    'lastModifiedAt': datetime.utcnow()
                }
            }
        )
        
        # Trigger background content generation
        from background_tasks import trigger_course_content_generation
        trigger_course_content_generation(
            current_app._get_current_object(),
            str(course_id),
            user_id,
            new_modules
        )
        
        return jsonify({
            'success': True,
            'message': result.get('message', 'Curriculum updated successfully!'),
            'curriculum': modified,
            'courseId': str(course_id)
        })
        
    except Exception as e:
        print(f"Modify curriculum error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@learning_bp.route('/course/<course_id>/module/<module_id>/generate', methods=['POST'])
def generate_module_submodules(course_id, module_id):
    """Generate submodules for a module on-demand."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    
    course = db.user_courses.find_one({'_id': ObjectId(course_id), 'userId': ObjectId(user_id)})
    if not course:
        return jsonify({'error': 'Course not found'}), 404
        
    # Find the module
    target_module = None
    module_index = -1
    for i, mod in enumerate(course['modules']):
        if str(mod['moduleId']) == module_id:
            target_module = mod
            module_index = i
            break
    
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
        
    # Check if already generated - only skip if subModules already exist
    if target_module.get('subModules') and len(target_module.get('subModules', [])) > 0:
        return jsonify({'message': 'Module already generated', 'module': target_module})
        
    # Generate submodules using prompts.py
    prompt = prompts.get_expand_module_prompt(
        module_title=target_module['title'],
        module_description=target_module['description'],
        course_topic=course['topic'],
        target_level=course.get('targetLevel', 'intermediate')
    )
    
    try:
        generated_submodules = AIService.generate_with_schema(prompt, prompts.SCHEMAS["submodules"])
        
        # Build submodule documents
        db_submodules = []
        for j, sub in enumerate(generated_submodules):
            db_submodules.append({
                'subModuleId': ObjectId(),
                'title': sub.get('title', ''),
                'description': sub.get('description', ''),
                'order': j + 1,
                'estimatedDuration': parse_duration(sub.get('estimated_time', '30 mins')),
                'isLocked': j > 0,
                'unlockedAt': datetime.utcnow() if j == 0 else None,
                'hasTest': False
            })
        
        # Update the module in the database
        db.user_courses.update_one(
            {'_id': ObjectId(course_id), 'modules.moduleId': ObjectId(module_id)},
            {
                '$set': {
                    f'modules.{module_index}.subModules': db_submodules,
                    f'modules.{module_index}.needsGeneration': False
                }
            }
        )
        
        # Fetch and return updated module
        updated_course = db.user_courses.find_one({'_id': ObjectId(course_id)})
        updated_module = updated_course['modules'][module_index]
        
        return jsonify({'message': 'Module generated', 'module': updated_module})
        
    except Exception as e:
        return jsonify({'error': f'Failed to generate module: {str(e)}'}), 500

def parse_duration(duration_str):
    """Parse duration string like '2 hours' or '30 mins' to minutes."""
    try:
        duration_str = duration_str.lower().strip()
        if 'hour' in duration_str:
            num = float(duration_str.split()[0])
            return int(num * 60)
        elif 'min' in duration_str:
            num = float(duration_str.split()[0])
            return int(num)
        else:
            return 30  # default
    except:
        return 30

@learning_bp.route('/courses', methods=['GET'])
def get_courses():
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        db = get_db()
        courses = list(db.user_courses.find({'userId': ObjectId(user_id)}).sort('createdAt', -1))
        
        # Get all progress tracking for this user
        progress_records = list(db.progress_tracking.find({'userId': ObjectId(user_id)}))
        progress_map = {}
        for p in progress_records:
            key = str(p.get('subModuleId'))
            progress_map[key] = p
        
        # Convert ObjectIds to strings for JSON and add quizPassed status
        for course in courses:
            course['_id'] = str(course['_id'])
            course['userId'] = str(course['userId'])
            if course.get('currentModuleId'):
                course['currentModuleId'] = str(course['currentModuleId'])
            if course.get('currentSubModuleId'):
                course['currentSubModuleId'] = str(course['currentSubModuleId'])
            
            for mod in course.get('modules', []):
                mod['moduleId'] = str(mod['moduleId'])
                if mod.get('parentModuleId'):
                    mod['parentModuleId'] = str(mod['parentModuleId'])
                mod['prerequisites'] = [str(p) for p in mod.get('prerequisites', [])]
                if mod.get('testId'):
                    mod['testId'] = str(mod['testId'])
                
                # Track if all submodule quizzes in this module are passed
                all_passed = True
                for sub in mod.get('subModules', []):
                    sub_id_str = str(sub['subModuleId'])
                    sub['subModuleId'] = sub_id_str
                    if sub.get('relatedToSubModuleId'):
                        sub['relatedToSubModuleId'] = str(sub['relatedToSubModuleId'])
                    if sub.get('createdAt'):
                        sub['createdAt'] = sub['createdAt'].isoformat() if hasattr(sub['createdAt'], 'isoformat') else str(sub['createdAt'])
                    
                    # Add quizPassed from progress tracking
                    progress = progress_map.get(sub_id_str, {})
                    sub['quizPassed'] = progress.get('quizPassed', False)
                    sub['contentCompleted'] = progress.get('contentCompleted', False)
                    sub['status'] = progress.get('status', 'not_started')
                    sub['testAttempts'] = progress.get('testAttempts', 0)
                    sub['bestTestScore'] = progress.get('bestTestScore', None)
                    
                    if not sub['quizPassed']:
                        all_passed = False

                
                # Module is considered passed if all submodule quizzes passed
                mod['quizPassed'] = all_passed if mod.get('subModules') else False
            
            # Calculate course progress based on contentCompleted submodules
            total_submodules = sum(len(mod.get('subModules', [])) for mod in course.get('modules', []))
            completed_submodules = 0
            for mod in course.get('modules', []):
                for sub in mod.get('subModules', []):
                    if sub.get('contentCompleted', False):
                        completed_submodules += 1
            
            course['completionPercentage'] = round((completed_submodules / total_submodules * 100) if total_submodules > 0 else 0, 1)
            course['completedSubmodules'] = completed_submodules
            course['totalSubmodules'] = total_submodules
        
        return jsonify({'courses': courses})


    except Exception as e:
        return jsonify({'error': str(e)}), 500


@learning_bp.route('/course/<course_id>/archive', methods=['POST'])
def archive_course(course_id):
    """Archive a course (hides from active list but preserves progress)."""
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        db = get_db()
        result = db.user_courses.update_one(
            {'_id': ObjectId(course_id), 'userId': ObjectId(user_id)},
            {'$set': {'isArchived': True, 'archivedAt': datetime.utcnow()}}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Course not found'}), 404
        
        return jsonify({'success': True, 'message': 'Course archived successfully'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@learning_bp.route('/course/<course_id>/unarchive', methods=['POST'])
def unarchive_course(course_id):
    """Unarchive a course (restores to active list with all progress intact)."""
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        db = get_db()
        result = db.user_courses.update_one(
            {'_id': ObjectId(course_id), 'userId': ObjectId(user_id)},
            {'$set': {'isArchived': False}, '$unset': {'archivedAt': ''}}
        )
        
        if result.matched_count == 0:
            return jsonify({'error': 'Course not found'}), 404
        
        return jsonify({'success': True, 'message': 'Course unarchived successfully'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@learning_bp.route('/course/<course_id>/generation-status', methods=['GET'])
def get_generation_status(course_id):
    """Get the content generation status for a course's modules and submodules."""
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        db = get_db()
        course = db.user_courses.find_one({
            '_id': ObjectId(course_id),
            'userId': ObjectId(user_id)
        })
        
        if not course:
            return jsonify({'error': 'Course not found'}), 404
        
        # Build status response
        modules_status = []
        for mod in course.get('modules', []):
            submodules_status = []
            for sub in mod.get('subModules', []):
                submodules_status.append({
                    'subModuleId': str(sub['subModuleId']),
                    'title': sub.get('title', ''),
                    'contentStatus': sub.get('contentStatus', 'pending'),
                    'quizStatus': sub.get('quizStatus', 'pending'),
                    'contentGeneratedAt': sub.get('contentGeneratedAt'),
                    'quizGeneratedAt': sub.get('quizGeneratedAt')
                })
            
            modules_status.append({
                'moduleId': str(mod['moduleId']),
                'title': mod.get('title', ''),
                'examStatus': mod.get('examStatus', 'pending'),
                'examGeneratedAt': mod.get('examGeneratedAt'),
                'submodules': submodules_status
            })
        
        return jsonify({
            'courseId': str(course_id),
            'modules': modules_status
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@learning_bp.route('/profile', methods=['GET'])
def get_profile():
    try:
        user_id = get_user_from_token()
        if not user_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        db = get_db()
        persona = db.user_personas.find_one({'userId': ObjectId(user_id), 'isActive': True})
        
        if not persona:
            return jsonify({'persona': None})
        
        # Convert ObjectIds to strings
        persona['_id'] = str(persona['_id'])
        persona['userId'] = str(persona['userId'])
        if persona.get('previousVersionId'):
            persona['previousVersionId'] = str(persona['previousVersionId'])
        if persona.get('lastUpdateTrigger', {}).get('eventId'):
            persona['lastUpdateTrigger']['eventId'] = str(persona['lastUpdateTrigger']['eventId'])
        
        return jsonify({'persona': persona})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_submodule_content(topic, submodule_title, user_level, submodule_description):
    """Generates detailed, high-quality learning content for a submodule using AI."""
    
    # Generate using clean prompt and structured schema
    prompt = prompts.get_submodule_content_prompt(
        topic=topic,
        submodule_title=submodule_title,
        user_level=user_level,
        context=submodule_description
    )
    
    try:
        content = AIService.generate_with_schema(prompt, prompts.SCHEMAS["submodule_content"])
        
        # Ensure all required fields exist
        if 'introduction' not in content:
            content['introduction'] = f"Welcome to {submodule_title}. Let's explore this topic together."
        if 'topics' not in content or not content['topics']:
            content['topics'] = []
        if 'summary' not in content:
            content['summary'] = f"This covered the key concepts of {submodule_title}."
            
        return content
        
    except Exception as e:
        print(f"Error generating submodule content: {e}")
        import traceback
        traceback.print_exc()
        
        # Return fallback content
        return {
            "introduction": f"Welcome to {submodule_title}. This content is being prepared.",
            "topics": [{
                "title": submodule_title,
                "content": f"# {submodule_title}\n\nContent generation encountered an issue. Please refresh the page to try again.",
                "comprehensionQuestion": {
                    "question": f"What is the main focus of {submodule_title}?",
                    "options": ["Option A", "Option B", "Option C", "Option D"],
                    "correctAnswer": "Option A",
                    "hint": "Think about the topic title and what it suggests."
                }
            }],
            "summary": f"Learn the fundamentals of {submodule_title}"
        }


def generate_submodule_test(topic, submodule_title, submodule_content, user_level):
    """Generates a test/quiz for a specific submodule based on its content."""
    
    # Build content summary from topics - with safety checks
    content_summary = ""
    
    if isinstance(submodule_content, dict):
        topics = submodule_content.get('topics', [])
        if isinstance(topics, list):
            for t in topics[:5]:
                if isinstance(t, dict):
                    title = t.get('title', 'Topic')
                    content = t.get('content', '')
                    if isinstance(content, str):
                        content_summary += f"- {title}: {content[:300]}...\n"
        
        if not content_summary:
            summary = submodule_content.get('summary', '')
            if isinstance(summary, str):
                content_summary = summary
    
    # If still no content summary, create one from the title
    if not content_summary:
        content_summary = f"This lesson covers the key concepts of {submodule_title} as part of learning {topic}."
    
    # Use clean prompt from prompts.py
    prompt = prompts.get_quiz_prompt(submodule_title, content_summary, user_level)
    
    try:
        quiz_data = AIService.generate_with_schema(prompt, prompts.SCHEMAS["quiz"])
        
        # Validate structure - handle both nested and flat responses
        if 'quiz' in quiz_data and isinstance(quiz_data['quiz'], dict):
            quiz_data = quiz_data['quiz']
        
        if 'questions' not in quiz_data or not quiz_data['questions']:
            raise ValueError("No questions generated")
        
        print(f"[Quiz] Generated {len(quiz_data['questions'])} questions for {submodule_title}")
        return quiz_data
        
    except Exception as e:
        print(f"Error generating test: {e}")
        import traceback
        traceback.print_exc()
        
        # Create a fallback quiz with basic questions about the topic
        return {
            "title": f"Quiz: {submodule_title}",
            "description": "Test your understanding of this lesson",
            "passingScore": 70,
            "questions": [
                {
                    "questionText": f"What is the main purpose of {submodule_title}?",
                    "type": "multiple_choice",
                    "options": [
                        f"To understand the core concepts of {submodule_title}",
                        "To memorize definitions without understanding",
                        "To skip ahead to advanced topics",
                        "None of the above"
                    ],
                    "correctAnswer": f"To understand the core concepts of {submodule_title}",
                    "explanation": f"The main goal is to build a solid understanding of {submodule_title} before moving forward.",
                    "hint": "Think about what you learned in this lesson.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"Why is understanding {submodule_title} important when learning {topic}?",
                    "type": "multiple_choice",
                    "options": [
                        f"It forms a foundation for more advanced concepts in {topic}",
                        "It is not important at all",
                        "It only matters for exams",
                        "It is optional knowledge"
                    ],
                    "correctAnswer": f"It forms a foundation for more advanced concepts in {topic}",
                    "explanation": f"{submodule_title} is a key building block in mastering {topic}.",
                    "hint": "Consider how this lesson connects to the broader course.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"Which approach is most effective for learning {submodule_title}?",
                    "type": "multiple_choice",
                    "options": [
                        "Read once and move on",
                        "Practice and apply concepts through examples",
                        "Skip the comprehension questions",
                        "Only look at the summary"
                    ],
                    "correctAnswer": "Practice and apply concepts through examples",
                    "explanation": "Active learning through practice helps reinforce understanding and retention.",
                    "hint": "Think about how you learn best.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"What should you do if you find a concept in {submodule_title} confusing?",
                    "type": "multiple_choice",
                    "options": [
                        "Skip it and hope it makes sense later",
                        "Review the content, use the hints, and ask questions",
                        "Give up on the topic",
                        "Assume it's not important"
                    ],
                    "correctAnswer": "Review the content, use the hints, and ask questions",
                    "explanation": "Taking time to understand confusing concepts builds a stronger foundation.",
                    "hint": "Think about effective study strategies.",
                    "difficulty": "medium"
                },
                {
                    "questionText": f"After completing {submodule_title}, what's the best next step?",
                    "type": "multiple_choice",
                    "options": [
                        "Immediately take the quiz to test understanding",
                        "Close the app and forget about it",
                        "Skip to an unrelated topic",
                        "Only read the flashcards"
                    ],
                    "correctAnswer": "Immediately take the quiz to test understanding",
                    "explanation": "Testing yourself right after learning helps identify gaps and reinforce knowledge.",
                    "hint": "Consider how testing improves learning.",
                    "difficulty": "easy"
                }
            ]
        }


def generate_module_exam(topic, module_title, submodule_contents, user_level):
    """Generates a comprehensive module exam based on all submodule contents."""
    
    # Create a summary of all content for AI to analyze
    content_summaries = []
    for item in submodule_contents:
        content = item.get('content', {})
        if isinstance(content, dict):
            intro = content.get('introduction', '')
            topics_text = ""
            for t in content.get('topics', [])[:3]:
                topics_text += f"{t.get('title', '')}: {t.get('content', '')[:200]}...\n"
            content_text = f"{intro}\n{topics_text}"
        else:
            content_text = str(content)[:800]
        content_summaries.append(f"SUBMODULE: {item['title']}\n{content_text}")
    
    combined_content = "\n\n".join(content_summaries)
    
    # Use prompts.py - AI will decide if coding questions are needed based on content
    prompt = prompts.get_module_exam_with_content_prompt(
        module_title=module_title,
        content_summaries=combined_content,
        user_level=user_level
    )
    
    try:
        exam_data = AIService.generate_with_schema(prompt, prompts.SCHEMAS["module_exam"])
        
        # Handle nested response
        if 'exam' in exam_data and isinstance(exam_data['exam'], dict):
            exam_data = exam_data['exam']
        if 'module_exam' in exam_data and isinstance(exam_data['module_exam'], dict):
            exam_data = exam_data['module_exam']
        
        # Validate structure
        if 'questions' not in exam_data or not exam_data['questions']:
            raise ValueError("No questions generated")
        
        print(f"[Exam] Generated {len(exam_data['questions'])} questions for {module_title}")
        
        # Ensure multi-select questions have correctAnswers array
        for q in exam_data.get('questions', []):
            if q.get('type') == 'multi-select' and not q.get('correctAnswers'):
                if q.get('correctAnswer'):
                    q['correctAnswers'] = [a.strip() for a in q['correctAnswer'].split(',')]
            
        return exam_data
        
    except Exception as e:
        print(f"Error generating module exam: {e}")
        import traceback
        traceback.print_exc()
        
        # Create fallback exam with basic questions
        submodule_titles = [item['title'] for item in submodule_contents[:3]] if submodule_contents else ['the topics']
        
        return {
            "title": f"Module Exam: {module_title}",
            "description": f"Comprehensive assessment of {module_title}",
            "passingScore": 70,
            "questions": [
                {
                    "questionText": f"What is the primary focus of the '{module_title}' module?",
                    "type": "multiple_choice",
                    "options": [
                        f"Understanding the core concepts of {module_title}",
                        "Memorizing definitions without context",
                        "Skipping to advanced topics",
                        "None of the above"
                    ],
                    "correctAnswer": f"Understanding the core concepts of {module_title}",
                    "explanation": f"The module {module_title} is designed to provide a solid foundation in its core concepts.",
                    "hint1": "Think about the main learning objectives of this module.",
                    "hint2": "Consider what the submodules covered.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"Which of the following is covered in this module?",
                    "type": "multiple_choice",
                    "options": [
                        submodule_titles[0] if len(submodule_titles) > 0 else "Topic 1",
                        "Unrelated topic",
                        "Something not in this module",
                        "None of the above"
                    ],
                    "correctAnswer": submodule_titles[0] if len(submodule_titles) > 0 else "Topic 1",
                    "explanation": f"This module covers {', '.join(submodule_titles)}.",
                    "hint1": "Recall the submodules you studied.",
                    "hint2": "Think about the main topics covered.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"Why is it important to complete all submodules before taking this exam?",
                    "type": "multiple_choice",
                    "options": [
                        "To build a complete understanding of the interconnected concepts",
                        "It's not important",
                        "Just for extra credit",
                        "To waste time"
                    ],
                    "correctAnswer": "To build a complete understanding of the interconnected concepts",
                    "explanation": "Each submodule builds upon previous ones, creating a comprehensive understanding.",
                    "hint1": "Consider how topics in the module relate to each other.",
                    "hint2": "Think about progressive learning.",
                    "difficulty": "easy"
                },
                {
                    "questionText": f"What is the best way to apply what you learned in {module_title}?",
                    "type": "multiple_choice",
                    "options": [
                        "Practice with real-world examples and projects",
                        "Only read the content once",
                        "Ignore the comprehension questions",
                        "Skip to the next module immediately"
                    ],
                    "correctAnswer": "Practice with real-world examples and projects",
                    "explanation": "Applying concepts through practice reinforces learning and builds practical skills.",
                    "hint1": "Think about effective learning strategies.",
                    "hint2": "Consider how professionals learn new skills.",
                    "difficulty": "medium"
                }
            ]
        }

@learning_bp.route('/course/<course_id>/module/<module_id>/submodule/<submodule_id>', methods=['GET'])
def get_submodule_details(course_id, module_id, submodule_id):
    print(f"\n=== GET SUBMODULE DETAILS ===")
    print(f"Course: {course_id}, Module: {module_id}, Submodule: {submodule_id}")
    
    user_id = get_user_from_token()
    if not user_id:
        print("ERROR: Unauthorized - no user_id")
        return jsonify({'error': 'Unauthorized'}), 401

    print(f"User ID: {user_id}")
    db = get_db()
    
    # 1. Verify access and get basic info from user_courses
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    
    if not course:
        print("ERROR: Course not found")
        return jsonify({'error': 'Course not found'}), 404

    print(f"Course found: {course.get('title', 'No title')}")

    # Find the specific module and submodule structure
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        print("ERROR: Module not found")
        return jsonify({'error': 'Module not found'}), 404
    
    print(f"Module found: {target_module.get('title', 'No title')}")
        
    target_submodule = next((s for s in target_module['subModules'] if str(s['subModuleId']) == submodule_id), None)
    if not target_submodule:
        print("ERROR: Submodule not found")
        return jsonify({'error': 'Submodule not found'}), 404

    print(f"Submodule found: {target_submodule.get('title', 'No title')}")

    # 2. Get or Generate Content
    content = db.submodule_contents.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    # Check if content is a failed fallback and needs regeneration
    needs_regeneration = False
    if content and content.get('textContent'):
        tc = content['textContent']
        if isinstance(tc, dict) and 'Content generation failed' in tc.get('summary', ''):
            needs_regeneration = True
            print("Content needs regeneration (previous failure)")

    if not content or needs_regeneration:
        print("Generating new content...")
        # Generate new content
        persona = db.user_personas.find_one({'userId': ObjectId(user_id)})
        user_level = "Intermediate" # Default
        if persona and 'topicProficiency' in persona:
            # Try to find level for this topic
            topic_prof = next((t for t in persona['topicProficiency'] if t['topicName'].lower() in course['topic'].lower()), None)
            if topic_prof:
                user_level = topic_prof['learningLevel']

        generated_data = generate_submodule_content(
            course['topic'], 
            target_submodule['title'], 
            user_level,
            target_submodule.get('description', '')
        )
        
        print(f"Generated content summary: {str(generated_data.get('summary', ''))[:100]}...")

        new_content = {
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'subModuleId': ObjectId(submodule_id),
            'textContent': generated_data,
            'files': [], # Placeholder for now
            'aiMetadata': {
                'modelUsed': current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash'),
                'generatedAt': datetime.utcnow()
            },
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        }
        
        # Use upsert to prevent duplicates
        db.submodule_contents.update_one(
            {
                'userCourseId': ObjectId(course_id),
                'subModuleId': ObjectId(submodule_id)
            },
            {'$set': new_content},
            upsert=True
        )
        content = new_content

    else:
        print("Using existing content from database")

    # 3. Get Progress (Create if not exists)
    progress = db.progress_tracking.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })

    if not progress:
        new_progress = {
            'userId': ObjectId(user_id),
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'subModuleId': ObjectId(submodule_id),
            'status': 'in_progress',
            'completionPercentage': 0,
            'timeSpent': 0,
            'chatMessageCount': 0,
            'startedAt': datetime.utcnow(),
            'lastAccessedAt': datetime.utcnow()
        }
        db.progress_tracking.insert_one(new_progress)
        progress = new_progress
        
        # Update course status to in_progress when first accessed
        db.user_courses.update_one(
            {'_id': ObjectId(course_id), 'status': 'not_started'},
            {'$set': {'status': 'in_progress', 'lastAccessedAt': datetime.utcnow()}}
        )
    else:
        # Update last accessed
        db.progress_tracking.update_one(
            {'_id': progress['_id']},
            {'$set': {'lastAccessedAt': datetime.utcnow()}}
        )
        # Update course last accessed
        db.user_courses.update_one(
            {'_id': ObjectId(course_id)},
            {'$set': {'lastAccessedAt': datetime.utcnow()}}
        )

    # 4. Convert ObjectIds for JSON response
    if '_id' in content:
        content['_id'] = str(content['_id'])

    content['userCourseId'] = str(content['userCourseId'])
    content['moduleId'] = str(content['moduleId'])
    content['subModuleId'] = str(content['subModuleId'])
    
    if progress.get('_id'):
        progress['_id'] = str(progress['_id'])
    if progress.get('userId'):
        progress['userId'] = str(progress['userId'])
    if progress.get('userCourseId'):
        progress['userCourseId'] = str(progress['userCourseId'])
    if progress.get('moduleId'):
        progress['moduleId'] = str(progress['moduleId'])
    if progress.get('subModuleId'):
        progress['subModuleId'] = str(progress['subModuleId'])
    
    # Convert ObjectId in structure
    structure_copy = dict(target_submodule)
    structure_copy['subModuleId'] = str(structure_copy.get('subModuleId', ''))
    if structure_copy.get('relatedToSubModuleId'):
        structure_copy['relatedToSubModuleId'] = str(structure_copy['relatedToSubModuleId'])
    
    # Convert ObjectIds in progress (including any new fields)
    if progress.get('relatedToSubModuleId'):
        progress['relatedToSubModuleId'] = str(progress['relatedToSubModuleId'])
    if progress.get('weakAreas'):
        # weakAreas is already a list of strings, no conversion needed
        pass

    response_data = {
        'structure': structure_copy,
        'content': content,
        'progress': progress
    }

    
    print(f"=== RESPONSE SUCCESS ===")
    print(f"Structure title: {structure_copy.get('title', 'N/A')}")
    print(f"Content has textContent: {bool(content.get('textContent'))}")
    print(f"Progress status: {progress.get('status', 'N/A')}")
    
    return jsonify(response_data)


@learning_bp.route('/course/<course_id>/module/<module_id>/submodule/<submodule_id>/download', methods=['GET'])
def download_submodule_content(course_id, module_id, submodule_id):
    """Download submodule content as PDF file."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    
    # Verify access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    # Get module and submodule info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
        
    target_submodule = next((s for s in target_module['subModules'] if str(s['subModuleId']) == submodule_id), None)
    if not target_submodule:
        return jsonify({'error': 'Submodule not found'}), 404

    # Get content
    content = db.submodule_contents.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    if not content or not content.get('textContent'):
        return jsonify({'error': 'Content not found'}), 404

    tc = content['textContent']
    
    # Generate PDF
    pdf = FPDF()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    # Title
    pdf.set_font('Helvetica', 'B', 20)
    title = target_submodule.get('title', 'Untitled')
    pdf.cell(0, 15, txt=title, ln=True, align='C')
    pdf.ln(5)
    
    # Course info
    pdf.set_font('Helvetica', 'I', 10)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 8, txt=f"Course: {course.get('title', 'Unknown')}", ln=True)
    pdf.cell(0, 8, txt=f"Module: {target_module.get('title', 'Unknown')}", ln=True)
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)
    
    def clean_text(text):
        """Remove markdown formatting for PDF."""
        if not text:
            return ""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '[Code Example]', text)
        # Remove inline code
        text = re.sub(r'`[^`]+`', lambda m: m.group(0)[1:-1], text)
        # Remove markdown headers
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        # Remove links
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Replace common unicode chars
        text = text.replace('•', '-').replace('—', '-').replace('’', "'").replace('“', '"').replace('”', '"')
        return text.strip()
    
    def add_section(title, content_text, is_list=False):
        pdf.set_font('Helvetica', 'B', 14)
        pdf.set_text_color(79, 70, 229)  # Indigo color
        pdf.cell(0, 12, txt=title, ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Helvetica', '', 11)
        
        # Calculate effective width
        epw = pdf.w - 40  # Width - left margin - right margin
        
        if is_list and isinstance(content_text, list):
            for item in content_text:
                if isinstance(item, str):
                    cleaned = clean_text(item)
                    if cleaned:
                        pdf.multi_cell(epw, 7, txt=f"- {cleaned}")
                elif isinstance(item, dict):
                    item_title = item.get('title', '')
                    if item_title:
                        pdf.set_font('Helvetica', 'B', 11)
                        pdf.multi_cell(epw, 7, txt=f"  {item_title}")
                        pdf.set_font('Helvetica', '', 11)
                    desc = item.get('description', '')
                    if desc:
                        pdf.multi_cell(epw, 7, txt=f"    {clean_text(desc)}")
        else:
            cleaned = clean_text(str(content_text) if content_text else "")
            if cleaned:
                pdf.multi_cell(epw, 7, txt=cleaned)
        pdf.ln(5)
    
    # Check if new format (topics array) or old format
    is_new_format = 'topics' in tc and isinstance(tc.get('topics'), list) and len(tc.get('topics', [])) > 0
    
    if is_new_format:
        # NEW FORMAT: introduction + topics array
        
        # Introduction
        if tc.get('introduction'):
            add_section("Introduction", tc.get('introduction'))
        
        # Topics
        topics = tc.get('topics', [])
        for idx, topic in enumerate(topics, 1):
            topic_title = topic.get('title', f'Topic {idx}')
            
            # Topic header
            pdf.set_font('Helvetica', 'B', 14)
            pdf.set_text_color(79, 70, 229)
            pdf.cell(0, 12, txt=f"{idx}. {topic_title}", ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.set_font('Helvetica', '', 11)
            
            # Topic content
            content = topic.get('content', '')
            if content:
                epw = pdf.w - 40
                cleaned = clean_text(content)
                if cleaned:
                    pdf.multi_cell(epw, 7, txt=cleaned)
                    pdf.ln(3)
            
            # Key points
            key_points = topic.get('keyPoints', [])
            if key_points:
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, txt="Key Points:", ln=True)
                pdf.set_font('Helvetica', '', 11)
                for point in key_points:
                    if isinstance(point, str):
                        cleaned = clean_text(point)
                        if cleaned:
                            pdf.multi_cell(epw, 7, txt=f"  - {cleaned}")
                pdf.ln(3)
            
            # Examples
            examples = topic.get('examples', [])
            if examples:
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, txt="Examples:", ln=True)
                pdf.set_font('Helvetica', '', 11)
                for ex in examples:
                    if isinstance(ex, dict):
                        ex_title = ex.get('title', '')
                        ex_desc = ex.get('description', '')
                        if ex_title:
                            pdf.set_font('Helvetica', 'B', 10)
                            pdf.multi_cell(epw, 7, txt=f"  {ex_title}")
                            pdf.set_font('Helvetica', '', 11)
                        if ex_desc:
                            pdf.multi_cell(epw, 7, txt=f"    {clean_text(ex_desc)}")
                    elif isinstance(ex, str):
                        pdf.multi_cell(epw, 7, txt=f"  - {clean_text(ex)}")
                pdf.ln(3)
            
            pdf.ln(5)
        
        # Key Takeaways
        if tc.get('keyTakeaways'):
            add_section("Key Takeaways", tc.get('keyTakeaways'), is_list=True)
    
    else:
        # OLD FORMAT: summary, detailedExplanation, etc.
        
        # Summary
        if tc.get('summary'):
            add_section("Summary", tc.get('summary'))
        
        # Detailed Explanation
        if tc.get('detailedExplanation'):
            add_section("Content", tc.get('detailedExplanation'))
        
        # Key Takeaways
        if tc.get('keyTakeaways'):
            add_section("Key Takeaways", tc.get('keyTakeaways'), is_list=True)
        
        # Examples
        if tc.get('examples'):
            add_section("Examples", tc.get('examples'), is_list=True)
        
        # Practice Exercises
        if tc.get('practiceExercises'):
            add_section("Practice Exercises", tc.get('practiceExercises'), is_list=True)
        
        # Resources
        if tc.get('resources'):
            add_section("Additional Resources", tc.get('resources'), is_list=True)
    
    # Footer
    pdf.ln(10)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 8, txt="Generated by MyEdBase - Personalized Learning Platform", ln=True, align='C')
    
    # Output to bytes
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    
    filename = f"{title.replace(' ', '_')}.pdf"
    
    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )


@learning_bp.route('/course/<course_id>/module/<module_id>/submodule/<submodule_id>/download-ppt', methods=['GET'])
def download_submodule_ppt(course_id, module_id, submodule_id):
    """Download submodule content as PPT presentation."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    
    # Verify access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Get module and submodule info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
    
    target_submodule = next((s for s in target_module['subModules'] if str(s['subModuleId']) == submodule_id), None)
    if not target_submodule:
        return jsonify({'error': 'Submodule not found'}), 404
    
    # Get content
    content_doc = db.submodule_contents.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    if not content_doc or not content_doc.get('textContent'):
        return jsonify({'error': 'Content not found. Complete the lesson first.'}), 404
    
    text_content = content_doc.get('textContent', {})
    
    # Generate PPT
    from ppt_generator import generate_submodule_ppt
    
    ppt_buffer = generate_submodule_ppt(
        course.get('title', 'Course'),
        target_module.get('title', 'Module'),
        target_submodule.get('title', 'Lesson'),
        text_content
    )
    
    # Create filename
    base_name = target_submodule.get('title', 'lesson').replace(' ', '_')
    filename = f"{base_name}_slides.pptx"
    
    return send_file(
        ppt_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        as_attachment=True,
        download_name=filename
    )


@learning_bp.route('/course/<course_id>/module/<module_id>/download-ppt', methods=['GET'])
def download_module_ppt(course_id, module_id):
    """Download entire module content as a combined PPT presentation."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    
    # Verify access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Get module info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
    
    # Collect all submodule content
    submodules_data = []
    for submodule in target_module.get('subModules', []):
        submodule_id = submodule.get('subModuleId')
        if not submodule_id:
            continue
            
        # Get content for this submodule
        content_doc = db.submodule_contents.find_one({
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(str(submodule_id))
        })
        
        text_content = {}
        if content_doc and content_doc.get('textContent'):
            text_content = content_doc.get('textContent', {})
        
        submodules_data.append({
            'title': submodule.get('title', 'Untitled'),
            'content': text_content
        })
    
    if not submodules_data:
        return jsonify({'error': 'No submodule content found for this module'}), 404
    
    # Generate PPT
    from ppt_generator import generate_module_ppt
    
    ppt_buffer = generate_module_ppt(
        course.get('title', 'Course'),
        target_module.get('title', 'Module'),
        submodules_data
    )
    
    # Create filename
    base_name = target_module.get('title', 'module').replace(' ', '_')
    filename = f"{base_name}_complete.pptx"
    
    return send_file(
        ppt_buffer,
        mimetype='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        as_attachment=True,
        download_name=filename
    )


@learning_bp.route('/course/<course_id>/module/<module_id>/flashcards', methods=['GET'])
def get_module_flashcards(course_id, module_id):
    """Generate flashcards from module content - no AI call, uses existing data."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    # Verify access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Get module info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
    
    flashcards = []
    
    # Extract flashcards from each submodule
    for submodule in target_module.get('subModules', []):
        submodule_id = submodule.get('subModuleId')
        submodule_title = submodule.get('title', 'Untitled')
        
        if not submodule_id:
            continue
        
        # Get content
        content_doc = db.submodule_contents.find_one({
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(str(submodule_id))
        })
        
        if not content_doc or not content_doc.get('textContent'):
            continue
        
        text_content = content_doc.get('textContent', {})
        
        # Check for new format (topics array)
        topics = text_content.get('topics', [])
        for topic in topics:
            topic_title = topic.get('title', 'Topic')
            
            # Use AI-generated flashcards if available
            topic_flashcards = topic.get('flashcards', [])
            for fc in topic_flashcards:
                if fc.get('front') and fc.get('back'):
                    flashcards.append({
                        'type': fc.get('type', 'definition'),
                        'front': fc.get('front', ''),
                        'back': fc.get('back', ''),
                        'submodule': submodule_title
                    })
            
            # Also add comprehension question as a quiz card
            question = topic.get('comprehensionQuestion', {})
            if question and question.get('question'):
                flashcards.append({
                    'type': 'question',
                    'front': question.get('question', ''),
                    'options': question.get('options', []),
                    'correctAnswer': question.get('correctAnswer', ''),
                    'hint': question.get('hint', ''),
                    'submodule': submodule_title
                })
        
        # Fallback for old format
        if not topics:
            summary = text_content.get('summary', '')
            if summary:
                flashcards.append({
                    'type': 'concept',
                    'front': submodule_title,
                    'back': summary,
                    'submodule': submodule_title
                })
    
    return jsonify({'flashcards': flashcards})


@learning_bp.route('/course/<course_id>/module/<module_id>/submodule/<submodule_id>/test', methods=['GET'])
def get_submodule_test(course_id, module_id, submodule_id):
    """Get or generate a test for a specific submodule."""
    print(f"\n=== GET SUBMODULE TEST ===")
    print(f"Course: {course_id}, Module: {module_id}, Submodule: {submodule_id}")
    
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    
    # Verify access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    # Get module and submodule info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
        
    target_submodule = next((s for s in target_module['subModules'] if str(s['subModuleId']) == submodule_id), None)
    if not target_submodule:
        return jsonify({'error': 'Submodule not found'}), 404

    # Check for existing test
    existing_test = db.submodule_tests.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    print(f"Existing test found: {existing_test is not None}")
    if existing_test:
        print(f"Existing test has questions: {len(existing_test.get('questions', []))}")
    
    if existing_test and existing_test.get('questions') and len(existing_test.get('questions')) > 0:
        print("Returning existing test from database")
        # Return existing test (without correct answers for security, unless already attempted)
        
        # Get previous attempt info
        progress = db.progress_tracking.find_one({
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(submodule_id)
        })
        
        has_previous_attempt = progress and progress.get('lastAttemptAnswers')
        
        # If user has attempted, include correct answers in response
        if has_previous_attempt:
            test_data = {
                'title': existing_test.get('title', f"Quiz: {target_submodule['title']}"),
                'description': existing_test.get('description', ''),
                'questions': [
                    {
                        'questionText': q['questionText'],
                        'options': q['options'],
                        'correctAnswer': q.get('correctAnswer'),
                        'explanation': q.get('explanation', '')
                    }
                    for q in existing_test.get('questions', [])
                ]
            }
        else:
            test_data = {
                'title': existing_test.get('title', f"Quiz: {target_submodule['title']}"),
                'description': existing_test.get('description', ''),
                'questions': [
                    {
                        'questionText': q['questionText'],
                        'options': q['options']
                    }
                    for q in existing_test.get('questions', [])
                ]
            }
        
        response = {
            'test': test_data,
            'previousBestScore': progress.get('bestTestScore') if progress else None,
            'attemptCount': progress.get('testAttempts', 0) if progress else 0,
            'isExisting': True
        }
        
        # Include previous attempt if exists
        if has_previous_attempt:
            response['previousAttempt'] = {
                'answers': progress.get('lastAttemptAnswers'),
                'results': progress.get('lastAttemptResults'),
                'score': progress.get('lastAttemptScore'),
                'passed': progress.get('lastAttemptPassed', False),
                'attemptedAt': progress.get('lastTestAt').isoformat() if progress.get('lastTestAt') else None
            }
        
        return jsonify(response)

    
    print("Generating new test...")
    # Generate new test
    content = db.submodule_contents.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    if not content or not content.get('textContent'):
        return jsonify({'error': 'Content not found. Complete the lesson first.'}), 400

    # Get user level
    persona = db.user_personas.find_one({'userId': ObjectId(user_id)})
    user_level = "Intermediate"
    if persona and 'topicProficiency' in persona:
        topic_prof = next((t for t in persona['topicProficiency'] if t['topicName'].lower() in course['topic'].lower()), None)
        if topic_prof:
            user_level = topic_prof['learningLevel']

    # Generate test
    test_data = generate_submodule_test(
        course['topic'],
        target_submodule['title'],
        content['textContent'],
        user_level
    )
    
    if not test_data.get('questions'):
        return jsonify({'error': 'Failed to generate test'}), 500

    print(f"Generated test with {len(test_data.get('questions', []))} questions")

    # Store the test using upsert to prevent duplicates
    new_test = {
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id),
        'subModuleId': ObjectId(submodule_id),
        'title': test_data.get('title', f"Quiz: {target_submodule['title']}"),
        'description': test_data.get('description', ''),
        'passingScore': test_data.get('passingScore', 70),
        'questions': test_data.get('questions', []),
        'createdAt': datetime.utcnow()
    }
    
    # Use update with upsert to ensure only one test per submodule
    db.submodule_tests.update_one(
        {
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(submodule_id)
        },
        {'$set': new_test},
        upsert=True
    )
    
    print("Test stored in database")
    
    # Return test without answers
    return jsonify({
        'test': {
            'title': new_test['title'],
            'description': new_test['description'],
            'questions': [
                {
                    'questionText': q['questionText'],
                    'options': q['options']
                }
                for q in new_test['questions']
            ]
        },
        'previousBestScore': None,
        'attemptCount': 0,
        'isExisting': False
    })



@learning_bp.route('/course/<course_id>/module/<module_id>/submodule/<submodule_id>/test/submit', methods=['POST'])
def submit_submodule_test(course_id, module_id, submodule_id):
    """Submit answers for a submodule test with adaptive learning logic."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    answers = data.get('answers', [])
    hints_used = data.get('hintsUsed', {})  # {question_index: {hint1: true, hint2: true}}
    
    if not answers:
        return jsonify({'error': 'No answers provided'}), 400

    db = get_db()
    
    # Get configuration thresholds
    pass_threshold = current_app.config.get('QUIZ_PASS_THRESHOLD', 70)
    retry_limit = current_app.config.get('SUBMODULE_FAIL_RETRY_LIMIT', 2)
    module_fail_threshold = current_app.config.get('MODULE_FAIL_THRESHOLD', 50)
    hint_penalty = 0.1  # 10% penalty per hint used
    
    # Get the test
    test = db.submodule_tests.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    if not test:
        return jsonify({'error': 'Test not found'}), 404

    # Get course structure
    course = db.user_courses.find_one({'_id': ObjectId(course_id)})
    if not course:
        return jsonify({'error': 'Course not found'}), 404
        
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404
        
    target_submodule = next((s for s in target_module['subModules'] if str(s['subModuleId']) == submodule_id), None)
    if not target_submodule:
        return jsonify({'error': 'Submodule not found'}), 404

    # Grade the test
    questions = test.get('questions', [])
    if len(answers) != len(questions):
        return jsonify({'error': 'Answer count mismatch'}), 400

    results = []
    correct_count = 0
    hint_penalty_total = 0
    weak_areas = []
    
    for i, (answer, question) in enumerate(zip(answers, questions)):
        is_correct = answer == question.get('correctAnswer')
        question_hints_used = hints_used.get(str(i), {})
        hint_count = sum(1 for v in question_hints_used.values() if v)
        
        if is_correct:
            correct_count += 1
            # Apply hint penalty to correct answers (each hint = 10% of that question's value)
            hint_penalty_total += hint_count * hint_penalty
        else:
            # Track weak areas based on wrong answers
            weak_areas.append(question.get('questionText', ''))
        
        results.append({
            'questionIndex': i,
            'isCorrect': is_correct,
            'userAnswer': answer,
            'correctAnswer': question.get('correctAnswer'),
            'explanation': question.get('explanation', ''),
            'hintsUsed': hint_count
        })
    
    # Calculate score with hint penalty
    base_score = (correct_count / len(questions)) * 100 if questions else 0
    penalty_deduction = (hint_penalty_total / len(questions)) * 100 if questions else 0
    score = max(0, base_score - penalty_deduction)
    passed = score >= pass_threshold
    
    # Get or create progress
    progress = db.progress_tracking.find_one({
        'userCourseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id)
    })
    
    if not progress:
        progress = {
            'userId': ObjectId(user_id),
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'subModuleId': ObjectId(submodule_id),
            'status': 'in_progress',
            'completionPercentage': 0,
            'testAttempts': 0,
            'submoduleFailCount': 0,
            'startedAt': datetime.utcnow()
        }
        db.progress_tracking.insert_one(progress)
        progress = db.progress_tracking.find_one({'subModuleId': ObjectId(submodule_id), 'userId': ObjectId(user_id)})
    
    attempt_count = progress.get('testAttempts', 0) + 1
    fail_count = progress.get('submoduleFailCount', 0)
    
    # Response object
    response_data = {
        'score': score,
        'passed': passed,
        'correctCount': correct_count,
        'totalQuestions': len(questions),
        'passingScore': pass_threshold,
        'results': results,
        'attemptCount': attempt_count,
        'action': None,  # Will be set based on logic
        'nextSubmodule': None,
        'remedialSubmodule': None,
        'message': ''
    }
    
    # Create attempt record for history
    attempt_record = {
        'attemptNumber': attempt_count,
        'score': score,
        'timestamp': datetime.utcnow(),
        'results': results,
        'passed': passed
    }
    
    if passed:
        # SUCCESS PATH: Update progress and unlock next submodule
        update_data = {
            'testAttempts': attempt_count,
            'lastTestAt': datetime.utcnow(),
            'testPassed': True,
            'quizPassed': True,  # Used for unlocking next content
            'status': 'completed',
            'completionPercentage': 100,
            'bestTestScore': max(progress.get('bestTestScore', 0), score),
            'lastAttemptScore': score,
            'lastAttemptAnswers': answers,
            'lastAttemptResults': results,
            'lastAttemptPassed': True
        }

        
        db.progress_tracking.update_one(
            {'_id': progress['_id']},
            {'$set': update_data, '$push': {'attemptHistory': attempt_record}}
        )

        # === GAMIFICATION: Award XP for quiz pass ===
        try:
            xp_type = 'quiz_perfect' if score == 100 else 'quiz_pass'
            award_xp(db, user_id, xp_type)
            update_streak(db, user_id)
            increment_stat(db, user_id, 'quizzesPassed')
            if score == 100:
                increment_stat(db, user_id, 'perfectScores')
        except Exception as e:
            print(f"Gamification error: {e}")  # Don't fail the main request
        
        # Find and unlock next submodule
        next_submodule = find_and_unlock_next_submodule(db, course, module_id, submodule_id, user_id)
        
        response_data['action'] = 'continue'
        response_data['message'] = 'Great job! You passed the quiz.'
        response_data['nextSubmodule'] = next_submodule
        
    else:
        # FAIL PATH: Track failure and determine action
        new_fail_count = fail_count + 1
        
        update_data = {
            'testAttempts': attempt_count,
            'lastTestAt': datetime.utcnow(),
            'submoduleFailCount': new_fail_count,
            'weakAreas': weak_areas[:3],  # Store top 3 weak areas
            'bestTestScore': max(progress.get('bestTestScore', 0), score),
            'lastAttemptScore': score,
            'lastAttemptAnswers': answers,
            'lastAttemptResults': results,
            'lastAttemptPassed': False
        }
        
        db.progress_tracking.update_one(
            {'_id': progress['_id']},
            {'$set': update_data, '$push': {'attemptHistory': attempt_record}}
        )

        
        # Check if remedial already generated for this submodule
        remedial_already_generated = progress.get('remedialSubmoduleGenerated', False)
        
        # Generate remedial after 1st failure (but only once)
        if new_fail_count >= 1 and not remedial_already_generated:
            # Generate remedial submodule
            persona = db.user_personas.find_one({'userId': ObjectId(user_id)})
            user_level = "Intermediate"
            if persona and 'topicProficiency' in persona:
                topic_prof = next((t for t in persona['topicProficiency'] if t['topicName'].lower() in course['topic'].lower()), None)
                if topic_prof:
                    user_level = topic_prof['learningLevel']
            
            remedial_submodule = generate_and_insert_remedial_submodule(
                db, course, target_module, target_submodule, 
                weak_areas, user_level, user_id
            )
            
            response_data['action'] = 'remedial'
            response_data['message'] = f"We've created a personalized review lesson to help you master this topic. You can also continue retrying the quiz."
            response_data['remedialSubmodule'] = remedial_submodule
            
            # Mark that remedial has been generated for this submodule
            db.progress_tracking.update_one(
                {'_id': progress['_id']},
                {'$set': {'remedialSubmoduleGenerated': True, 'remedialSubmoduleId': str(remedial_submodule['subModuleId']) if remedial_submodule else None}}
            )
        else:
            # Allow retry (unlimited retries)
            response_data['action'] = 'retry'
            if remedial_already_generated:
                response_data['message'] = f'Score: {score:.0f}%. You need {pass_threshold}% to pass. Review the remedial lesson or try again.'
            else:
                response_data['message'] = f'Score: {score:.0f}%. You need {pass_threshold}% to pass. Review the material and try again.'
    
    # Log activity
    log_activity(user_id, 'quiz_submitted', {
        'score': round(score, 1),
        'passed': passed,
        'attemptCount': attempt_count,
        'correctCount': correct_count,
        'totalQuestions': len(questions)
    }, course_id=course_id, module_id=module_id, submodule_id=submodule_id)
    
    # Track hints used for badges
    total_hints_used = sum(sum(1 for v in hints_used.get(str(i), {}).values() if v) for i in range(len(questions)))
    if total_hints_used > 0:
        increment_stat(db, user_id, 'hintsUsed', total_hints_used)
        check_and_award_badges(db, user_id)
    
    # Check module-level performance
    check_module_level_performance(db, course, module_id, user_id, module_fail_threshold)
    
    return jsonify(response_data)


# ============ MODULE EXAM ENDPOINTS ============

@learning_bp.route('/course/<course_id>/module/<module_id>/exam', methods=['GET'])
def get_module_exam(course_id, module_id):
    """Get or generate a module-level exam that tests all submodules."""
    print(f"\n=== GET MODULE EXAM ===")
    print(f"Course: {course_id}, Module: {module_id}")
    
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    db = get_db()
    
    # Verify course access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404

    # Get module info
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404

    # Check for existing module exam
    existing_exam = db.module_exams.find_one({
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id)
    })
    
    # Get module progress
    module_progress = db.module_progress.find_one({
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id),
        'userId': ObjectId(user_id)
    })
    
    has_previous_attempt = module_progress and module_progress.get('lastAttemptAnswers')
    
    if existing_exam and existing_exam.get('questions') and len(existing_exam.get('questions')) > 0:
        print("Returning existing module exam from database")
        print(f"[DEBUG] Exam has {len(existing_exam.get('questions', []))} questions")
        if existing_exam.get('questions'):
            q0 = existing_exam['questions'][0]
            print(f"[DEBUG] First question keys: {list(q0.keys())}")
            print(f"[DEBUG] First question type: {q0.get('type')}")
            print(f"[DEBUG] First question options: {q0.get('options', 'NO OPTIONS')}")
            print(f"[DEBUG] First question hint1: {q0.get('hint1', 'NO HINT1')}")
        
        if has_previous_attempt:
            test_data = {
                'title': existing_exam.get('title', f"Module Exam: {target_module['title']}"),
                'description': existing_exam.get('description', 'Complete this exam to unlock the next module.'),
                'questions': [
                    {
                        'type': q.get('type', 'multiple-choice'),
                        'questionText': q.get('questionText') or q.get('question', 'Question'),
                        'options': q.get('options', []),
                        'correctAnswer': q.get('correctAnswer'),
                        'correctAnswers': q.get('correctAnswers', []),
                        'explanation': q.get('explanation', ''),
                        'hint1': q.get('hint1', 'Think carefully about the concepts covered.'),
                        'hint2': q.get('hint2', 'Review the main topics from this module.'),
                        'difficulty': q.get('difficulty', 'medium')
                    }
                    for q in existing_exam.get('questions', [])
                ]
            }
        else:
            test_data = {
                'title': existing_exam.get('title', f"Module Exam: {target_module['title']}"),
                'description': existing_exam.get('description', 'Complete this exam to unlock the next module.'),
                'questions': [
                    {
                        'type': q.get('type', 'multiple-choice'),
                        'questionText': q.get('questionText') or q.get('question', 'Question'),
                        'options': q.get('options', []),
                        'hint1': q.get('hint1', 'Think carefully about the concepts covered.'),
                        'hint2': q.get('hint2', 'Review the main topics from this module.'),
                        'difficulty': q.get('difficulty', 'medium')
                    }
                    for q in existing_exam.get('questions', [])
                ]
            }

        
        response = {
            'exam': test_data,
            'previousBestScore': module_progress.get('bestExamScore') if module_progress else None,
            'attemptCount': module_progress.get('examAttempts', 0) if module_progress else 0,
            'isExisting': True,
            'modulePassed': module_progress.get('examPassed', False) if module_progress else False
        }
        
        if has_previous_attempt:
            response['previousAttempt'] = {
                'answers': module_progress.get('lastAttemptAnswers'),
                'results': module_progress.get('lastAttemptResults'),
                'score': module_progress.get('lastAttemptScore'),
                'passed': module_progress.get('lastAttemptPassed', False),
                'attemptedAt': module_progress.get('lastExamAt').isoformat() if module_progress.get('lastExamAt') else None
            }
        
        return jsonify(response)
    
    print("Generating new module exam...")
    
    # Gather content from all submodules for this module
    submodule_contents = []
    for sub in target_module.get('subModules', []):
        content = db.submodule_contents.find_one({
            'userCourseId': ObjectId(course_id),
            'subModuleId': sub['subModuleId']
        })
        if content and content.get('textContent'):
            submodule_contents.append({
                'title': sub['title'],
                'content': content['textContent']
            })
    
    if not submodule_contents:
        return jsonify({'error': 'No content found. Complete at least one submodule first.'}), 400

    # Get user level
    persona = db.user_personas.find_one({'userId': ObjectId(user_id)})
    user_level = "Intermediate"
    if persona and 'topicProficiency' in persona:
        topic_prof = next((t for t in persona['topicProficiency'] if t['topicName'].lower() in course['topic'].lower()), None)
        if topic_prof:
            user_level = topic_prof['learningLevel']

    # Generate module exam
    exam_data = generate_module_exam(
        course['topic'],
        target_module['title'],
        submodule_contents,
        user_level
    )
    
    if not exam_data.get('questions'):
        return jsonify({'error': 'Failed to generate exam'}), 500

    print(f"Generated module exam with {len(exam_data.get('questions', []))} questions")

    # Store the exam
    new_exam = {
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id),
        'title': exam_data.get('title', f"Module Exam: {target_module['title']}"),
        'description': exam_data.get('description', 'Complete this exam to unlock the next module.'),
        'passingScore': exam_data.get('passingScore', 70),
        'questions': exam_data.get('questions', []),
        'createdAt': datetime.utcnow()
    }
    
    db.module_exams.update_one(
        {
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id)
        },
        {'$set': new_exam},
        upsert=True
    )
    
    print("Module exam stored in database")
    
    return jsonify({
        'exam': {
            'title': new_exam.get('title', f"Module Exam"),
            'description': new_exam.get('description', 'Complete this exam to unlock the next module.'),
            'questions': [
                {
                    'type': q.get('type', 'multiple-choice'),
                    'questionText': q.get('questionText') or q.get('question', 'Question'),
                    'options': q.get('options', []),
                    'hint1': q.get('hint1', 'Think carefully about the concepts covered.'),
                    'hint2': q.get('hint2', 'Review the main topics from this module.'),
                    'difficulty': q.get('difficulty', 'medium')
                }
                for q in new_exam.get('questions', [])
            ]

        },
        'previousBestScore': None,
        'attemptCount': 0,
        'isExisting': False,
        'modulePassed': False
    })


def generate_remedial_module(db, course_id, module_id, user_id, module_progress):
    """Generate a personalized remedial module based on student's performance."""
    try:
        # Get the course and module information
        course = db.user_courses.find_one({'_id': ObjectId(course_id)})
        if not course:
            return None
            
        target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
        if not target_module:
            return None
        
        # Analyze attempt history
        attempt_history = module_progress.get('attemptHistory', [])
        if not attempt_history:
            return None
        
        # Identify weak areas from all attempts
        all_wrong_questions = []
        
        for attempt in attempt_history:
            for result in attempt.get('results', []):
                if not result.get('isCorrect', False):
                    all_wrong_questions.append({
                        'question': result.get('questionText', 'N/A'),
                        'userAnswer': result.get('userAnswer', 'N/A'),
                        'correctAnswer': result.get('correctAnswer', 'N/A'),
                        'type': result.get('type', 'N/A'),
                        'feedback': result.get('feedback', 'N/A')
                    })
        
        # Get submodule quiz results for this module
        submodule_results = []
        for submodule in target_module.get('subModules', []):
            quiz_results = db.quiz_results.find({
                'userId': ObjectId(user_id),
                'subModuleId': submodule.get('subModuleId')
            }).sort('timestamp', -1).limit(1)
            
            for qr in quiz_results:
                submodule_results.append({
                    'submoduleTitle': submodule.get('title', 'N/A'),
                    'score': qr.get('score', 0),
                    'passed': qr.get('passed', False),
                    'weakAreas': [r.get('questionText', 'N/A') for r in qr.get('results', []) if not r.get('isCorrect', False)]
                })
        
        # Generate remedial content using prompts.py
        failed_topics = [target_module.get('title', 'N/A')]
        wrong_answers = all_wrong_questions[:10]
        
        prompt = prompts.get_remedial_module_prompt(
            module_title=target_module.get('title', 'Module Review'),
            failed_topics=failed_topics,
            wrong_answers=[q.get('questionText', '') for q in wrong_answers]
        )
        
        remedial_data = AIService.generate_with_schema(prompt, prompts.SCHEMAS["remedial_module"])
        
        # Create remedial module in database
        remedial_module_id = ObjectId()
        remedial_submodules = []
        
        for idx, sub_data in enumerate(remedial_data.get('subModules', [])):
            submodule_id = ObjectId()
            
            # Create the submodule entry for course structure
            remedial_submodules.append({
                'subModuleId': submodule_id,
                'title': sub_data.get('title', f'Review Lesson {idx + 1}'),
                'description': sub_data.get('description', ''),
                'isLocked': False,
                'status': 'not_started',
                'needsGeneration': False
            })
            
            # Create submodule_contents document so UI can display the content
            submodule_content = {
                'userCourseId': ObjectId(course_id),
                'moduleId': remedial_module_id,
                'subModuleId': submodule_id,
                'textContent': {
                    'introduction': sub_data.get('description', ''),
                    'topics': [{
                        'title': sub_data.get('title', f'Review Lesson {idx + 1}'),
                        'content': sub_data.get('content', ''),
                        'comprehensionQuestion': None,
                        'flashcards': []
                    }],
                    'summary': '',
                    'realWorldApplications': []
                },
                'isRemedial': True,
                'aiMetadata': {
                    'modelUsed': current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash'),
                    'generatedAt': datetime.utcnow()
                },
                'createdAt': datetime.utcnow()
            }
            db.submodule_contents.insert_one(submodule_content)
            print(f"[Remedial] Created submodule_contents for: {sub_data.get('title')}")
        
        remedial_module = {
            'moduleId': remedial_module_id,
            'title': remedial_data.get('moduleTitle', f"Review: {target_module.get('title')}"),
            'description': f"Personalized review module to help you master the content from {target_module.get('title')}",
            'isRemedial': True,
            'parentModuleId': ObjectId(module_id),
            'subModules': remedial_submodules,
            'needsGeneration': False,
            'quizPassed': False
        }
        
        # Add remedial module to course structure (after the original module)
        modules_list = course.get('modules', [])
        target_index = next((i for i, m in enumerate(modules_list) if str(m['moduleId']) == module_id), -1)
        
        print(f"[Remedial] Target index: {target_index}, inserting remedial module after {target_module.get('title')}")
        
        if target_index >= 0:
            modules_list.insert(target_index + 1, remedial_module)
            db.user_courses.update_one(
                {'_id': ObjectId(course_id)},
                {'$set': {'modules': modules_list}}
            )
            print(f"[Remedial] Inserted remedial module with {len(remedial_submodules)} submodules")
        
        # Mark that remedial module has been generated for this module
        db.module_progress.update_one(
            {'_id': module_progress['_id']},
            {'$set': {
                'remedialModuleGenerated': True,
                'remedialModuleId': remedial_module_id
            }}
        )
        
        print(f"[Remedial] Success! Remedial module ID: {remedial_module_id}")
        return remedial_module
        
    except Exception as e:
        print(f"[Remedial] Error in generate_remedial_module: {e}")
        import traceback
        traceback.print_exc()
        return None


@learning_bp.route('/course/<course_id>/module/<module_id>/exam/submit', methods=['POST'])

def submit_module_exam(course_id, module_id):
    """Submit answers for a module exam."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    answers = data.get('answers', [])
    hints_used = data.get('hintsUsed', {})  # {question_index: {hint1: true, hint2: true}}
    
    if not answers:
        return jsonify({'error': 'No answers provided'}), 400

    db = get_db()
    
    pass_threshold = current_app.config.get('QUIZ_PASS_THRESHOLD', 70)
    hint_penalty = 0.1  # 10% penalty per hint used
    
    # Get the exam
    exam = db.module_exams.find_one({
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id)
    })
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404

    # Get course structure
    course = db.user_courses.find_one({'_id': ObjectId(course_id)})
    if not course:
        return jsonify({'error': 'Course not found'}), 404
        
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return jsonify({'error': 'Module not found'}), 404

    # Grade the exam
    questions = exam.get('questions', [])
    if len(answers) != len(questions):
        return jsonify({'error': 'Answer count mismatch'}), 400

    results = []
    total_score = 0
    
    for i, (answer, question) in enumerate(zip(answers, questions)):
        q_type = question.get('type', 'multiple-choice')
        question_hints_used = hints_used.get(str(i), {})
        hint_count = sum(1 for v in question_hints_used.values() if v)
        hint_penalty_multiplier = 1 - (hint_count * hint_penalty)  # 0.9 for 1 hint, 0.8 for 2 hints
        
        if q_type == 'multiple-choice':
            is_correct = answer == question.get('correctAnswer')
            base_score = 100 if is_correct else 0
            score_for_q = base_score * hint_penalty_multiplier if is_correct else 0
            
            # Ensure explanation is a string
            raw_explanation = question.get('explanation', '')
            explanation = str(raw_explanation) if isinstance(raw_explanation, (str, int, float)) else 'See the correct answer above.'
            
            results.append({
                'questionIndex': i,
                'type': q_type,
                'isCorrect': is_correct,
                'userAnswer': answer,
                'correctAnswer': question.get('correctAnswer'),
                'explanation': explanation,
                'score': score_for_q,
                'hintsUsed': hint_count,
                'feedback': 'Correct!' if is_correct else 'Incorrect.'
            })
            total_score += score_for_q
        
        elif q_type == 'multi-select':
            # Parse user's comma-separated selections into a set
            user_selections = set(s.strip() for s in answer.split(',') if s.strip()) if answer else set()
            
            # Get correct answers - either from correctAnswers array or comma-separated correctAnswer
            correct_answers_list = question.get('correctAnswers', [])
            if not correct_answers_list and question.get('correctAnswer'):
                correct_answers_list = [s.strip() for s in question.get('correctAnswer', '').split(',')]
            correct_set = set(correct_answers_list)
            
            # Calculate score based on overlap
            is_exact_match = user_selections == correct_set
            if is_exact_match:
                base_score = 100
            else:
                # Partial credit: points for correct picks minus points for wrong picks
                correct_picks = len(user_selections & correct_set)
                wrong_picks = len(user_selections - correct_set)
                missed_picks = len(correct_set - user_selections)
                max_possible = len(correct_set)
                base_score = max(0, ((correct_picks - wrong_picks) / max_possible) * 100) if max_possible > 0 else 0
            
            score_for_q = base_score * hint_penalty_multiplier
            
            raw_explanation = question.get('explanation', '')
            explanation = str(raw_explanation) if isinstance(raw_explanation, (str, int, float)) else 'See the correct answer above.'
            
            results.append({
                'questionIndex': i,
                'type': q_type,
                'isCorrect': is_exact_match,
                'userAnswer': answer,
                'correctAnswer': ', '.join(correct_answers_list),
                'explanation': explanation,
                'score': score_for_q,
                'hintsUsed': hint_count,
                'feedback': 'All correct!' if is_exact_match else f'Partial credit. Correct answers: {", ".join(correct_answers_list)}'
            })
            total_score += score_for_q
            
        else: # short-answer or coding
            # Use AI to grade with prompts.py
            grading_prompt = prompts.get_grade_answer_prompt(
                question=question.get('questionText', ''),
                correct_answer=question.get('correctAnswer', ''),
                student_answer=answer
            )
            try:
                grade_data = AIService.generate_with_schema(grading_prompt, prompts.SCHEMAS["grade_answer"])
                base_score = grade_data.get('score', 0)
                # Apply hint penalty to short-answer/coding questions too
                score_for_q = base_score * hint_penalty_multiplier
                
                # Ensure feedback is a string, not an object
                raw_feedback = grade_data.get('feedback', '')
                if isinstance(raw_feedback, dict):
                    # Convert object to readable string
                    feedback = '. '.join(f"{k}: {v}" for k, v in raw_feedback.items() if isinstance(v, str))
                else:
                    feedback = str(raw_feedback) if raw_feedback else 'Answer graded.'
                
                results.append({
                    'questionIndex': i,
                    'type': q_type,
                    'isCorrect': score_for_q >= 70,
                    'userAnswer': answer,
                    'correctAnswer': question.get('correctAnswer'),
                    'explanation': str(question.get('explanation', '')) if question.get('explanation') else '',
                    'score': score_for_q,
                    'hintsUsed': hint_count,
                    'feedback': feedback
                })
                total_score += score_for_q
                
            except Exception as e:
                print(f"Error grading question {i}: {e}")
                # Fallback if AI fails
                results.append({
                    'questionIndex': i,
                    'type': q_type,
                    'isCorrect': False,
                    'userAnswer': answer,
                    'correctAnswer': question.get('correctAnswer'),
                    'explanation': question.get('explanation', ''),
                    'score': 0,
                    'feedback': "Error grading answer. Please contact support."
                })

    score = total_score / len(questions) if questions else 0
    passed = score >= pass_threshold
    
    # Calculate correct count
    correct_count = sum(1 for r in results if r.get('isCorrect', False))

    
    # Get or create module progress

    module_progress = db.module_progress.find_one({
        'userCourseId': ObjectId(course_id),
        'moduleId': ObjectId(module_id),
        'userId': ObjectId(user_id)
    })
    
    if not module_progress:
        module_progress = {
            'userId': ObjectId(user_id),
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'examAttempts': 0,
            'startedAt': datetime.utcnow()
        }
        db.module_progress.insert_one(module_progress)
        module_progress = db.module_progress.find_one({
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'userId': ObjectId(user_id)
        })
    
    
    attempt_count = module_progress.get('examAttempts', 0) + 1
    
    # Store this attempt in history
    attempt_record = {
        'attemptNumber': attempt_count,
        'score': score,
        'timestamp': datetime.utcnow(),
        'results': results,
        'passed': passed
    }
    
    response_data = {
        'score': score,
        'passed': passed,
        'correctCount': correct_count,
        'totalQuestions': len(questions),
        'passingScore': pass_threshold,
        'results': results,
        'attemptCount': attempt_count,
        'remedialModuleGenerated': False,
        'nextModule': None,
        'message': ''
    }
    
    if passed:
        # Update module progress as passed
        update_data = {
            'examAttempts': attempt_count,
            'lastExamAt': datetime.utcnow(),
            'examPassed': True,
            'bestExamScore': max(module_progress.get('bestExamScore', 0), score),
            'lastAttemptScore': score,
            'lastAttemptAnswers': answers,
            'lastAttemptResults': results,
            'lastAttemptPassed': True,
            '$push': {'attemptHistory': attempt_record}
        }
        
        db.module_progress.update_one(
            {'_id': module_progress['_id']},
            {'$set': {k: v for k, v in update_data.items() if k != '$push'}, '$push': update_data['$push']}
        )
        
        # Mark all submodules in this module as completed
        modules = course.get('modules', [])
        current_module = next((m for m in modules if str(m['moduleId']) == module_id), None)
        if current_module and current_module.get('subModules'):
            for submod in current_module['subModules']:
                submodule_id = str(submod.get('subModuleId'))
                if submodule_id:
                    # Update or create progress tracking for each submodule
                    db.progress_tracking.update_one(
                        {
                            'userId': ObjectId(user_id),
                            'courseId': ObjectId(course_id),
                            'moduleId': ObjectId(module_id),
                            'subModuleId': ObjectId(submodule_id)
                        },
                        {
                            '$set': {
                                'contentCompleted': True,
                                'contentCompletedAt': datetime.utcnow(),
                                'completedViaExam': True,
                                'updatedAt': datetime.utcnow()
                            },
                            '$setOnInsert': {
                                'userId': ObjectId(user_id),
                                'courseId': ObjectId(course_id),
                                'moduleId': ObjectId(module_id),
                                'subModuleId': ObjectId(submodule_id),
                                'createdAt': datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
        
        response_data['action'] = 'continue'
        
        # Find and unlock next module
        modules = course.get('modules', [])
        current_index = next((i for i, m in enumerate(modules) if str(m['moduleId']) == module_id), -1)
        
        if current_index >= 0 and current_index < len(modules) - 1:
            next_module = modules[current_index + 1]
            response_data['nextModule'] = {
                'moduleId': str(next_module['moduleId']),
                'title': next_module.get('title', ''),
                'subModuleId': str(next_module['subModules'][0]['subModuleId']) if next_module.get('subModules') else None
            }
            response_data['message'] = f"🎉 Congratulations! You passed the module exam. You've unlocked: {next_module.get('title', 'Next Module')}"
            
            # Trigger background content generation for the newly unlocked module
            from background_tasks import generate_module_content_background
            generate_module_content_background(
                current_app._get_current_object(),
                course_id,
                str(next_module['moduleId']),
                user_id,
                current_index + 1
            )
        else:
            response_data['message'] = "🎉 Congratulations! You've completed all modules in this course!"
    else:
        # Failed attempt
        update_data = {
            'examAttempts': attempt_count,
            'lastExamAt': datetime.utcnow(),
            'bestExamScore': max(module_progress.get('bestExamScore', 0), score),
            'lastAttemptScore': score,
            'lastAttemptAnswers': answers,
            'lastAttemptResults': results,
            'lastAttemptPassed': False,
            '$push': {'attemptHistory': attempt_record}
        }
        
        db.module_progress.update_one(
            {'_id': module_progress['_id']},
            {'$set': {k: v for k, v in update_data.items() if k != '$push'}, '$push': update_data['$push']}
        )
        
        # Generate remedial module after 2 failed attempts (but allow unlimited retries)
        remedial_threshold = 2
        if attempt_count >= remedial_threshold and not module_progress.get('remedialModuleGenerated', False):
            # Generate remedial module to help the student
            response_data['action'] = 'remedial'
            try:
                remedial_module = generate_remedial_module(db, course_id, module_id, user_id, module_progress)
                if remedial_module:
                    response_data['remedialModuleGenerated'] = True
                    response_data['remedialModuleId'] = str(remedial_module['moduleId'])
                    response_data['message'] = f"Score: {score:.0f}%. A personalized review module has been created to help you. You can still retry the exam."
                else:
                    response_data['message'] = f"Score: {score:.0f}%. You need {pass_threshold}% to pass. Keep trying!"
            except Exception as e:
                print(f"Error generating remedial module: {e}")
                response_data['message'] = f"Score: {score:.0f}%. You need {pass_threshold}% to pass. Keep trying!"
        else:
            # Allow unlimited retries
            response_data['action'] = 'retry'
            response_data['message'] = f"Score: {score:.0f}%. You need {pass_threshold}% to pass. Review the material and try again."
    
    return jsonify(response_data)



def find_and_unlock_next_submodule(db, course, module_id, current_submodule_id, user_id):
    """Find and unlock the next submodule after completing current one."""
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return None

    
    submodules = target_module.get('subModules', [])
    current_index = next((i for i, s in enumerate(submodules) if str(s['subModuleId']) == current_submodule_id), -1)
    
    if current_index >= 0 and current_index < len(submodules) - 1:
        # Unlock next submodule in same module
        next_submodule = submodules[current_index + 1]
        next_submodule_id = next_submodule['subModuleId']
        
        db.user_courses.update_one(
            {
                '_id': course['_id'],
                'modules.subModules.subModuleId': next_submodule_id
            },
            {
                '$set': {
                    'modules.$[].subModules.$[sub].isLocked': False,
                    'modules.$[].subModules.$[sub].unlockedAt': datetime.utcnow()
                }
            },
            array_filters=[{'sub.subModuleId': next_submodule_id}]
        )
        
        return {
            'subModuleId': str(next_submodule_id),
            'title': next_submodule.get('title', ''),
            'moduleId': module_id
        }
    else:
        # Module complete, try to unlock next module
        modules = course.get('modules', [])
        module_index = next((i for i, m in enumerate(modules) if str(m['moduleId']) == module_id), -1)
        
        if module_index >= 0 and module_index < len(modules) - 1:
            next_module = modules[module_index + 1]
            if next_module.get('subModules'):
                first_submodule = next_module['subModules'][0]
                
                db.user_courses.update_one(
                    {
                        '_id': course['_id'],
                        'modules.subModules.subModuleId': first_submodule['subModuleId']
                    },
                    {
                        '$set': {
                            'modules.$[].subModules.$[sub].isLocked': False,
                            'modules.$[].subModules.$[sub].unlockedAt': datetime.utcnow()
                        }
                    },
                    array_filters=[{'sub.subModuleId': first_submodule['subModuleId']}]
                )
                
                return {
                    'subModuleId': str(first_submodule['subModuleId']),
                    'title': first_submodule.get('title', ''),
                    'moduleId': str(next_module['moduleId']),
                    'newModule': True,
                    'moduleName': next_module.get('name', '')
                }
    
    return None  # Course complete


def generate_and_insert_remedial_submodule(db, course, target_module, failed_submodule, weak_areas, user_level, user_id):
    """Generate and insert a remedial submodule to help user understand weak areas."""
    
    submodule_title = failed_submodule['title']
    topic = course['topic']
    
    # Use prompts.py for remedial content
    prompt = prompts.get_remedial_content_prompt(
        submodule_title=submodule_title,
        weak_areas=[submodule_title],
        user_level=user_level
    )
    
    print(f"Generating remedial content for: {submodule_title}")
    
    try:
        remedial_content = AIService.generate_with_schema(prompt, prompts.SCHEMAS["remedial_content"])
        print(f"Successfully generated remedial content")
        
    except Exception as e:
        print(f"Error generating remedial content: {e}")
        print(f"Response was: {response_text[:500] if 'response_text' in dir() else 'No response'}")
        
        # Create meaningful fallback content that teaches the actual topic
        remedial_content = {
            "summary": f"Let's take a fresh look at {submodule_title}. This time, we're going to slow way down and explain everything step by step. Don't worry about the quiz - understanding takes time, and sometimes a different approach makes all the difference. By the end of this review, you'll have a much clearer understanding of the key concepts.",
            "detailedExplanation": f"""# {submodule_title} - Simplified

## What is This About?

{submodule_title} is a fundamental concept in {topic}. Let's break it down into simple terms that anyone can understand.

## Why Does This Matter?

Understanding this concept is essential because it forms the foundation for more advanced topics. Once you truly grasp this, everything else becomes easier.

## The Core Idea

Think of it like this: imagine you're organizing your room. You wouldn't put everything in one giant pile - you'd organize things logically. That's essentially what {submodule_title} helps us do with our code and thinking.

## Step-by-Step Breakdown

**Step 1: Start Simple**
Begin with the most basic example. Don't try to understand everything at once.

**Step 2: Build Understanding**
Once the simple case makes sense, add one small piece at a time.

**Step 3: Practice**
Write your own examples. Even simple ones help reinforce the concepts.

**Step 4: Connect the Dots**
Think about how this relates to things you already know.

## Common Mistakes to Avoid

1. **Rushing ahead** - Take your time with each concept
2. **Memorizing without understanding** - Focus on *why*, not just *how*
3. **Skipping practice** - Hands-on experience is crucial

## Key Takeaway

{submodule_title} is all about writing cleaner, more maintainable code. When you get it right, your code becomes easier to read, test, and modify.

## What To Do Next

1. Read through this lesson slowly
2. Try the examples yourself
3. Create your own small examples
4. Review until comfortable before retaking the quiz""",
            "keyTakeaways": [
                f"Understanding {submodule_title} makes code cleaner and more maintainable",
                "Take your time - rushing leads to confusion",
                "Practice with simple examples before complex ones",
                "Focus on understanding WHY, not just HOW",
                "Connect new concepts to things you already know",
                "Making mistakes is part of learning",
                "Review material as many times as needed"
            ],
            "examples": [
                "Start with the simplest possible example and build from there",
                "Try modifying working examples to see what happens",
                "Create your own mini-project using these concepts"
            ],
            "resources": []
        }
    
    # Create new remedial submodule
    remedial_submodule_id = ObjectId()
    remedial_submodule = {
        'subModuleId': remedial_submodule_id,
        'title': f"Review: {submodule_title}",
        'description': f"A focused, step-by-step review of {submodule_title} with simpler explanations.",
        'duration': 15,
        'isLocked': False,
        'isRemedial': True,
        'relatedToSubModuleId': failed_submodule['subModuleId'],
        'createdAt': datetime.utcnow()
    }
    
    # Find position to insert (right after the failed submodule)
    submodules = target_module.get('subModules', [])
    current_index = next((i for i, s in enumerate(submodules) if s['subModuleId'] == failed_submodule['subModuleId']), -1)
    
    # Insert into course structure
    db.user_courses.update_one(
        {
            '_id': course['_id'],
            'modules.moduleId': target_module['moduleId']
        },
        {
            '$push': {
                'modules.$.subModules': {
                    '$each': [remedial_submodule],
                    '$position': current_index + 1  # Insert right after failed submodule
                }
            }
        }
    )
    
    # Create content for remedial submodule
    new_content = {
        'userCourseId': course['_id'],
        'moduleId': target_module['moduleId'],
        'subModuleId': remedial_submodule_id,
        'textContent': remedial_content,
        'isRemedial': True,

        'aiMetadata': {
            'modelUsed': current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash'),
            'generatedAt': datetime.utcnow()
        },
        'createdAt': datetime.utcnow()
    }
    db.submodule_contents.insert_one(new_content)
    
    return {
        'subModuleId': str(remedial_submodule_id),
        'title': remedial_submodule['title'],
        'moduleId': str(target_module['moduleId']),
        'isRemedial': True
    }


def check_module_level_performance(db, course, module_id, user_id, fail_threshold):
    """Check if overall module performance is poor and generate remedial module if needed."""
    
    target_module = next((m for m in course['modules'] if str(m['moduleId']) == module_id), None)
    if not target_module:
        return
    
    # Get all progress for this module's submodules
    non_remedial_submodules = [s for s in target_module.get('subModules', []) if not s.get('isRemedial')]
    
    if not non_remedial_submodules:
        return
    
    total_score = 0
    scored_count = 0
    
    for submodule in non_remedial_submodules:
        progress = db.progress_tracking.find_one({
            'userCourseId': course['_id'],
            'subModuleId': submodule['subModuleId']
        })
        
        if progress and progress.get('bestTestScore', 0) > 0:
            total_score += progress.get('bestTestScore', 0)
            scored_count += 1
    
    if scored_count == 0:
        return
    
    average_score = total_score / scored_count
    
    # If module average is below threshold and this is the last submodule being tested
    if average_score < fail_threshold and scored_count == len(non_remedial_submodules):
        # Check if remedial module already exists for this user
        existing_remedial = db.user_courses.find_one({
            '_id': course['_id'],
            'modules': {
                '$elemMatch': {
                    'isRemedialModule': True,
                    'relatedToModuleId': ObjectId(module_id)
                }
            }
        })
        
        if not existing_remedial:
            # Generate remedial module (this is a heavy operation, could be async)
            print(f"Module average ({average_score:.0f}%) below threshold ({fail_threshold}%). Consider generating remedial module.")
            # For now, just log - full module generation is complex and could be done on-demand



@learning_bp.route('/chat/message', methods=['POST'])
def send_chat_message():
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    course_id = data.get('courseId')
    module_id = data.get('moduleId')
    submodule_id = data.get('subModuleId')
    message_content = data.get('message')
    context_section = data.get('contextSection', 'general')

    if not all([course_id, module_id, submodule_id, message_content]):
        return jsonify({'error': 'Missing required fields'}), 400

    db = get_db()

    # Get user persona for context
    persona = db.user_personas.find_one({'userId': ObjectId(user_id), 'isActive': True})
    user_level = "Intermediate"
    learning_style = "balanced"
    if persona:
        # Get topic-specific level
        topic_profs = persona.get('topicProficiency', [])
        course = db.user_courses.find_one({'_id': ObjectId(course_id)})
        if course and topic_profs:
            for tp in topic_profs:
                if tp.get('topicName', '').lower() in course.get('topic', '').lower():
                    user_level = tp.get('learningLevel', 'Intermediate')
                    break
        learning_style = persona.get('interactionPreferences', {}).get('responseFormatPreference', 'balanced')

    # 1. Get or Create Active Chat Session
    chat_session = db.chats.find_one({
        'userId': ObjectId(user_id),
        'subModuleId': ObjectId(submodule_id),
        'isActive': True
    })

    if not chat_session:
        # Fetch context for the new session
        content = db.submodule_contents.find_one({
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(submodule_id)
        })
        
        # Get submodule structure for title
        course = db.user_courses.find_one({'_id': ObjectId(course_id)})
        submodule_title = ""
        course_topic = course.get('topic', '') if course else ""
        if course:
            for mod in course.get('modules', []):
                for sub in mod.get('subModules', []):
                    if str(sub['subModuleId']) == submodule_id:
                        submodule_title = sub.get('title', '')
                        break
        
        new_session = {
            'userId': ObjectId(user_id),
            'userCourseId': ObjectId(course_id),
            'moduleId': ObjectId(module_id),
            'subModuleId': ObjectId(submodule_id),
            'messages': [],
            'sessionStart': datetime.utcnow(),
            'lastMessageAt': datetime.utcnow(),
            'isActive': True,
            'contextSnapshot': {
                'subModuleTitle': submodule_title,
                'courseTopic': course_topic,
                'subModuleContent': content['textContent'].get('detailedExplanation', '') if content else "",
                'subModuleSummary': content['textContent'].get('summary', '') if content else "",
                'keyTakeaways': content['textContent'].get('keyTakeaways', []) if content else [],
                'userLevel': user_level
            },
            'totalMessages': 0,
            'userMessageCount': 0,
            'assistantMessageCount': 0,
            'chatAnalytics': {
                'questionTypes': [],
                'topicsAsked': []
            }
        }
        result = db.chats.insert_one(new_session)
        chat_session = new_session
        chat_session['_id'] = result.inserted_id

    # 2. Add User Message
    user_msg_obj = {
        'messageId': ObjectId(),
        'role': 'user',
        'content': message_content,
        'timestamp': datetime.utcnow(),
        'relatedContent': {
            'contentSection': context_section
        }
    }
    
    db.chats.update_one(
        {'_id': chat_session['_id']},
        {
            '$push': {'messages': user_msg_obj},
            '$set': {'lastMessageAt': datetime.utcnow()},
            '$inc': {'totalMessages': 1, 'userMessageCount': 1}
        }
    )

    # 3. Generate AI Response with Enhanced Context
    history = chat_session.get('messages', [])
    history.append(user_msg_obj)
    
    # Keep last 10 messages for context window
    recent_history = history[-10:]
    history_text = "\n".join([f"{'Student' if m['role']=='user' else 'AI Tutor'}: {m['content']}" for m in recent_history])
    
    context = chat_session.get('contextSnapshot', {})
    key_points = "\n".join([f"- {kp}" for kp in context.get('keyTakeaways', [])[:5]])
    
    # Build content context for the tutor
    content_context = f"""Lesson: {context.get('subModuleTitle', 'Unknown')}
Summary: {context.get('subModuleSummary', 'No summary available.')[:500]}
Key Points: {key_points}"""
    
    # Use prompts.py for chat tutor
    system_prompt = prompts.get_chat_tutor_prompt(
        topic=context.get('courseTopic', 'this topic'),
        content_context=content_context,
        chat_history=history_text,
        user_message=message_content
    )
    
    try:
        ai_response_text = AIService.generate_content(system_prompt)
    except Exception as e:
        print(f"Chat AI error: {e}")
        ai_response_text = "I'm having trouble connecting right now. Please try again in a moment."

    ai_msg_obj = {
        'messageId': ObjectId(),
        'role': 'assistant',
        'content': ai_response_text,
        'timestamp': datetime.utcnow(),
        'aiMetadata': {
            'modelUsed': current_app.config.get('GEMINI_MODEL', 'gemini-2.0-flash')
        }
    }

    db.chats.update_one(
        {'_id': chat_session['_id']},
        {
            '$push': {'messages': ai_msg_obj},
            '$set': {'lastMessageAt': datetime.utcnow()},
            '$inc': {'totalMessages': 1, 'assistantMessageCount': 1}
        }
    )
    
    # 4. Update User Persona with Chat Activity
    # Check if user is asking many questions (indicates potential weak area)
    total_questions = chat_session.get('userMessageCount', 0) + 1
    if total_questions >= 3 and persona:
        # Update persona to indicate high chat dependency for this topic
        submodule_title = context.get('subModuleTitle', '')
        if submodule_title:
            db.user_personas.update_one(
                {'_id': persona['_id']},
                {
                    '$set': {
                        'interactionPreferences.chatUsageFrequency': 'high' if total_questions >= 5 else 'medium',
                        'lastChatActivity': datetime.utcnow()
                    },
                    '$addToSet': {
                        'topicsWithHighChatUsage': submodule_title
                    }
                }
            )
    
    # 5. Update progress tracking
    db.progress_tracking.update_one(
        {
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(submodule_id)
        },
        {
            '$inc': {'chatMessageCount': 1},
            '$set': {'chatOpened': True, 'lastChatAt': datetime.utcnow()}
        },
        upsert=True
    )
    
    # Track chat message for badges
    increment_stat(db, user_id, 'chatMessages', 1)
    check_and_award_badges(db, user_id)

    return jsonify({
        'response': ai_response_text,
        'messageId': str(ai_msg_obj['messageId'])
    })


@learning_bp.route('/chat/history/<submodule_id>', methods=['GET'])
def get_chat_history(submodule_id):
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    
    # Get active session first, or most recent inactive one
    chat_session = db.chats.find_one(
        {
            'userId': ObjectId(user_id),
            'subModuleId': ObjectId(submodule_id)
        },
        sort=[('lastMessageAt', -1)]
    )
    
    if not chat_session:
        return jsonify({'messages': [], 'sessionId': None})
        
    # Convert ObjectIds
    messages = chat_session.get('messages', [])
    for m in messages:
        if 'messageId' in m:
            m['messageId'] = str(m['messageId'])
            
    return jsonify({
        'messages': messages,
        'sessionId': str(chat_session['_id'])
    })

@learning_bp.route('/chat/conversations/<submodule_id>', methods=['GET'])
def get_chat_conversations(submodule_id):
    """Get all chat conversations for a submodule."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    # Get all chat sessions for this submodule
    sessions = list(db.chats.find(
        {
            'userId': ObjectId(user_id),
            'subModuleId': ObjectId(submodule_id)
        },
        sort=[('lastMessageAt', -1)]
    ))
    
    conversations = []
    for session in sessions:
        # Get preview from first user message
        messages = session.get('messages', [])
        preview = ''
        for m in messages:
            if m.get('role') == 'user':
                preview = m.get('content', '')[:50] + ('...' if len(m.get('content', '')) > 50 else '')
                break
        
        conversations.append({
            'sessionId': str(session['_id']),
            'preview': preview or 'Conversation',
            'messageCount': len(messages),
            'lastMessageAt': session.get('lastMessageAt', session.get('sessionStart')).isoformat() if session.get('lastMessageAt') or session.get('sessionStart') else None,
            'isActive': session.get('isActive', False)
        })
    
    return jsonify({'conversations': conversations})

@learning_bp.route('/chat/session/<session_id>', methods=['GET'])
def get_chat_session(session_id):
    """Load a specific chat session."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    session = db.chats.find_one({
        '_id': ObjectId(session_id),
        'userId': ObjectId(user_id)
    })
    
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    messages = session.get('messages', [])
    for m in messages:
        if 'messageId' in m:
            m['messageId'] = str(m['messageId'])
    
    return jsonify({
        'messages': messages,
        'sessionId': str(session['_id'])
    })


@learning_bp.route('/chat/feedback', methods=['POST'])
def submit_chat_feedback():
    """Handle user feedback on AI responses."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    submodule_id = data.get('subModuleId')
    message_id = data.get('messageId')
    was_helpful = data.get('wasHelpful')
    
    if not submodule_id or not message_id or was_helpful is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    db = get_db()
    
    # Update the specific message in the chat session
    result = db.chats.update_one(
        {
            'userId': ObjectId(user_id),
            'subModuleId': ObjectId(submodule_id),
            'messages.messageId': ObjectId(message_id)
        },
        {
            '$set': {
                'messages.$.feedback': {
                    'wasHelpful': was_helpful,
                    'feedbackTimestamp': datetime.utcnow()
                }
            }
        }
    )
    
    # If not helpful, update persona to track topics needing better explanations
    if not was_helpful:
        chat = db.chats.find_one({
            'userId': ObjectId(user_id),
            'subModuleId': ObjectId(submodule_id)
        })
        if chat:
            submodule_title = chat.get('contextSnapshot', {}).get('subModuleTitle', '')
            if submodule_title:
                db.user_personas.update_one(
                    {'userId': ObjectId(user_id), 'isActive': True},
                    {
                        '$addToSet': {
                            'topicsNeedingBetterExplanation': submodule_title
                        }
                    }
                )
    
    return jsonify({'success': True})

@learning_bp.route('/chat/new', methods=['POST'])
def start_new_conversation():
    """Archive current chat and allow starting fresh."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    submodule_id = data.get('subModuleId')
    
    if not submodule_id:
        return jsonify({'error': 'Missing subModuleId'}), 400
    
    db = get_db()
    
    # Archive the current active chat
    db.chats.update_one(
        {
            'userId': ObjectId(user_id),
            'subModuleId': ObjectId(submodule_id),
            'isActive': True
        },
        {
            '$set': {
                'isActive': False,
                'closedAt': datetime.utcnow(),
                'closedReason': 'user_started_new_conversation'
            }
        }
    )
    
    return jsonify({'success': True, 'message': 'New conversation started'})

@learning_bp.route('/validate-syntax', methods=['POST'])
def validate_syntax():
    """Validate code syntax."""
    data = request.json
    code = data.get('code', '')
    language = data.get('language', 'python')
    
    if not code:
        return jsonify({'errors': []})
        
    errors = []
    
    if language.lower() == 'python':
        try:
            import ast
            ast.parse(code)
        except SyntaxError as e:
            errors.append({
                'startLineNumber': e.lineno,
                'startColumn': e.offset,
                'endLineNumber': e.lineno,
                'endColumn': e.offset + 1 if e.offset else 1,
                'message': f"Syntax Error: {e.msg}",
                'severity': 8 # MarkerSeverity.Error
            })
        except Exception as e:
            errors.append({
                'startLineNumber': 1,
                'startColumn': 1,
                'endLineNumber': 1,
                'endColumn': 1,
                'message': f"Error: {str(e)}",
                'severity': 8
            })
            
    return jsonify({'errors': errors})

@learning_bp.route('/submodule/complete', methods=['POST'])


def complete_submodule():
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.json
    course_id = data.get('courseId')
    module_id = data.get('moduleId')
    submodule_id = data.get('subModuleId')
    
    db = get_db()
    
    # 1. Update Progress - mark content as completed
    db.progress_tracking.update_one(
        {
            'userCourseId': ObjectId(course_id),
            'subModuleId': ObjectId(submodule_id)
        },
        {
            '$set': {
                'status': 'in_progress',  # Keep as in_progress until quiz is passed
                'contentCompleted': True,  # Track content completion separately
                'contentCompletedAt': datetime.utcnow()
            }
        },
        upsert=True
    )
    
    # === GAMIFICATION: Award XP for lesson completion ===
    try:
        award_xp(db, user_id, 'lesson_complete')
        update_streak(db, user_id)
        increment_stat(db, user_id, 'lessonsCompleted')
    except Exception as e:
        print(f"Gamification error: {e}")  # Don't fail the main request
    
    # 2. Unlock Next Submodule (Logic to find next one)
    course = db.user_courses.find_one({'_id': ObjectId(course_id)})
    if course:
        found_current = False
        next_submodule_id = None
        
        for module in course['modules']:
            for sub in module['subModules']:
                if found_current:
                    next_submodule_id = sub['subModuleId']
                    break
                if str(sub['subModuleId']) == submodule_id:
                    found_current = True
            if next_submodule_id:
                break
        
        if next_submodule_id:
            # Unlock it
            db.user_courses.update_one(
                {
                    '_id': ObjectId(course_id),
                    'modules.subModules.subModuleId': next_submodule_id
                },
                {
                    '$set': {
                        'modules.$[].subModules.$[sub].isLocked': False,
                        'modules.$[].subModules.$[sub].unlockedAt': datetime.utcnow()
                    }
                },
                array_filters=[{'sub.subModuleId': next_submodule_id}]
            )
            
    return jsonify({'success': True})

# ============ NOTES ENDPOINTS ============

@learning_bp.route('/course/<course_id>/notes', methods=['GET'])
def get_course_notes(course_id):
    """Get all notes for a course."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    # Verify course access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Get all notes for this course
    notes = list(db.course_notes.find({
        'userId': ObjectId(user_id),
        'courseId': ObjectId(course_id)
    }).sort('updatedAt', -1))
    
    # Convert ObjectIds
    for note in notes:
        note['_id'] = str(note['_id'])
        note['userId'] = str(note['userId'])
        note['courseId'] = str(note['courseId'])
        if note.get('subModuleId'):
            note['subModuleId'] = str(note['subModuleId'])
        if note.get('createdAt'):
            note['createdAt'] = note['createdAt'].isoformat()
        if note.get('updatedAt'):
            note['updatedAt'] = note['updatedAt'].isoformat()
    
    return jsonify({'notes': notes})

@learning_bp.route('/course/<course_id>/saved-message-ids', methods=['GET'])
def get_saved_message_ids(course_id):
    """Get all saved message IDs for AI chat notes."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    submodule_id = request.args.get('subModuleId')
    
    db = get_db()
    
    # Build query
    query = {
        'userId': ObjectId(user_id),
        'courseId': ObjectId(course_id),
        'source': 'ai_tutor',
        'messageId': {'$ne': None}
    }
    
    if submodule_id:
        query['subModuleId'] = ObjectId(submodule_id)
    
    # Get all notes with messageIds
    notes = list(db.course_notes.find(query, {'messageId': 1}))
    
    message_ids = [note['messageId'] for note in notes if note.get('messageId')]
    
    return jsonify({'savedMessageIds': message_ids})

@learning_bp.route('/course/<course_id>/notes', methods=['POST'])
def create_note(course_id):
    """Create a new note for a course."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    content = data.get('content', '').strip()
    title = data.get('title', 'Untitled Note').strip()
    submodule_id = data.get('subModuleId')
    source = data.get('source', 'manual')  # 'manual' or 'ai_tutor'
    message_id = data.get('messageId')  # For AI chat messages
    
    if not content:
        return jsonify({'error': 'Note content is required'}), 400
    
    db = get_db()
    
    # Verify course access
    course = db.user_courses.find_one({
        '_id': ObjectId(course_id),
        'userId': ObjectId(user_id)
    })
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Check if note with this messageId already exists (toggle behavior)
    if message_id:
        existing_note = db.course_notes.find_one({
            'userId': ObjectId(user_id),
            'courseId': ObjectId(course_id),
            'messageId': message_id
        })
        if existing_note:
            # Delete existing note (unsave)
            db.course_notes.delete_one({'_id': existing_note['_id']})
            return jsonify({'deleted': True, 'noteId': str(existing_note['_id'])}), 200
    
    new_note = {
        'userId': ObjectId(user_id),
        'courseId': ObjectId(course_id),
        'subModuleId': ObjectId(submodule_id) if submodule_id else None,
        'title': title,
        'content': content,
        'source': source,
        'messageId': message_id,  # Store messageId for AI chat messages
        'tags': data.get('tags', []),
        'createdAt': datetime.utcnow(),
        'updatedAt': datetime.utcnow()
    }
    
    result = db.course_notes.insert_one(new_note)
    new_note['_id'] = str(result.inserted_id)
    new_note['userId'] = str(new_note['userId'])
    new_note['courseId'] = str(new_note['courseId'])
    if new_note.get('subModuleId'):
        new_note['subModuleId'] = str(new_note['subModuleId'])
    new_note['createdAt'] = new_note['createdAt'].isoformat()
    new_note['updatedAt'] = new_note['updatedAt'].isoformat()
    
    # Track note creation for badges
    increment_stat(db, user_id, 'notesCreated', 1)
    check_and_award_badges(db, user_id)
    
    return jsonify({'note': new_note}), 201

@learning_bp.route('/notes/<note_id>', methods=['PUT'])
def update_note(note_id):
    """Update an existing note."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.json
    
    db = get_db()
    
    # Find note and verify ownership
    note = db.course_notes.find_one({
        '_id': ObjectId(note_id),
        'userId': ObjectId(user_id)
    })
    
    if not note:
        return jsonify({'error': 'Note not found'}), 404
    
    update_data = {'updatedAt': datetime.utcnow()}
    if 'content' in data:
        update_data['content'] = data['content'].strip()
    if 'title' in data:
        update_data['title'] = data['title'].strip()
    if 'tags' in data:
        update_data['tags'] = data['tags']
    
    db.course_notes.update_one(
        {'_id': ObjectId(note_id)},
        {'$set': update_data}
    )
    
    # Return updated note
    updated_note = db.course_notes.find_one({'_id': ObjectId(note_id)})
    updated_note['_id'] = str(updated_note['_id'])
    updated_note['userId'] = str(updated_note['userId'])
    updated_note['courseId'] = str(updated_note['courseId'])
    if updated_note.get('subModuleId'):
        updated_note['subModuleId'] = str(updated_note['subModuleId'])
    updated_note['createdAt'] = updated_note['createdAt'].isoformat()
    updated_note['updatedAt'] = updated_note['updatedAt'].isoformat()
    
    return jsonify({'note': updated_note})

@learning_bp.route('/notes/<note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a note."""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    
    db = get_db()
    
    # Find note and verify ownership
    result = db.course_notes.delete_one({
        '_id': ObjectId(note_id),
        'userId': ObjectId(user_id)
    })
    
    if result.deleted_count == 0:
        return jsonify({'error': 'Note not found'}), 404
    
    return jsonify({'success': True})
