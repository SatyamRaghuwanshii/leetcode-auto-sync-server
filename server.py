from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import html
import requests
import base64

app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": ["https://leetcode.com"]
    }
})


# ============================================================
# CONFIG
# ============================================================

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "SatyamRaghuwanshii")
GITHUB_REPO = os.environ.get(
    "GITHUB_REPO",
    "YOUR_LEETCODE_SOLUTIONS_REPOSITORY"
)
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"

GITHUB_API = "https://api.github.com"


# ============================================================
# GitHub helpers
# ============================================================

def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def github_url(path):
    return f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{path}"


def github_file_exists(path):
    response = requests.get(
        github_url(path),
        headers=github_headers(),
        params={"ref": GITHUB_BRANCH},
        timeout=15
    )

    if response.status_code == 200:
        return response.json()

    if response.status_code == 404:
        return None

    response.raise_for_status()


def create_github_file(path, content, message):
    encoded_content = base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")

    response = requests.put(
        github_url(path),
        headers=github_headers(),
        json={
            "message": message,
            "content": encoded_content,
            "branch": GITHUB_BRANCH
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# LeetCode
# ============================================================

def fetch_question(slug):

    query = """
    query questionData($titleSlug: String!) {

        question(titleSlug: $titleSlug) {

            questionFrontendId
            title
            titleSlug
            difficulty
            content
            isPaidOnly

        }

    }
    """

    response = requests.post(
        LEETCODE_GRAPHQL,
        json={
            "query": query,
            "variables": {
                "titleSlug": slug
            }
        },
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()

    question = data["data"]["question"]

    if not question:
        raise Exception("LeetCode question not found")

    return question


# ============================================================
# Create problem information
# ============================================================

def create_problem(data):

    number = int(data["questionFrontendId"])

    title = data["title"]

    slug = data["titleSlug"]

    difficulty = data["difficulty"]

    content = data["content"]

    folder = f"{number:04d}-{slug}"

    java_file = f"{folder}.java"

    java_path = f"{folder}/{java_file}"

    readme_path = f"{folder}/README.md"

    return {
        "number": number,
        "title": title,
        "slug": slug,
        "difficulty": difficulty,
        "content": content,
        "folder": folder,
        "java_path": java_path,
        "readme_path": readme_path
    }


# ============================================================
# Health check
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "success": True,
        "message": "LeetCode Auto Sync Server is running"
    })


# ============================================================
# Sync endpoint
# ============================================================

@app.route("/submit", methods=["POST"])
def submit():

    data = request.get_json()

    if not data:

        return jsonify({
            "success": False,
            "error": "No JSON data received"
        }), 400


    print("\n========================================")
    print("New LeetCode submission")
    print("========================================")

    print(data)


    # ========================================================
    # Only save accepted submissions
    # ========================================================

    if data.get("status") != "Accepted":

        print(
            f"Submission status: {data.get('status')}"
        )

        return jsonify({
            "success": True,
            "message": "Submission not accepted. Nothing pushed."
        })


    # ========================================================
    # Required fields
    # ========================================================

    slug = data.get("slug")

    code = data.get("code")

    runtime = data.get("runtime", "")

    runtime_percentile = data.get(
        "runtimePercentile",
        ""
    )

    memory = data.get("memory", "")

    memory_percentile = data.get(
        "memoryPercentile",
        ""
    )

    submission_id = data.get(
        "submissionId",
        ""
    )


    if not slug or not code:

        return jsonify({
            "success": False,
            "error": "Missing slug or code"
        }), 400


    # ========================================================
    # Check GitHub configuration
    # ========================================================

    if not GITHUB_TOKEN:

        return jsonify({
            "success": False,
            "error": "GITHUB_TOKEN is not configured"
        }), 500


    # ========================================================
    # Get LeetCode problem information
    # ========================================================

    try:

        question = fetch_question(slug)

    except Exception as e:

        print(
            "LeetCode API error:",
            e
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


    problem = create_problem(question)


    # ========================================================
    # Don't overwrite existing solution
    # ========================================================

    try:

        existing_file = github_file_exists(
            problem["java_path"]
        )

    except Exception as e:

        print(
            "GitHub check error:",
            e
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


    if existing_file:

        print(
            "\nSolution already exists:"
        )

        print(
            problem["java_path"]
        )

        return jsonify({
            "success": False,
            "error": "Solution already exists"
        }), 409


    # ========================================================
    # Create README
    # ========================================================

    readme = (
        f'<h2>'
        f'<a href="https://leetcode.com/problems/'
        f'{problem["slug"]}">'
        f'{problem["number"]}. '
        f'{html.escape(problem["title"])}'
        f'</a>'
        f'</h2>'

        f'<h3>'
        f'{problem["difficulty"]}'
        f'</h3>'

        f'<hr>'

        f'{problem["content"]}\n'
    )


    # ========================================================
    # Commit Java solution
    # ========================================================

    commit_message = (
        f"Time: {runtime} "
        f"({runtime_percentile}), "
        f"Space: {memory} "
        f"({memory_percentile}) - LeetHub"
    )


    print(
        "\nUploading Java solution..."
    )

    try:

        create_github_file(
            problem["java_path"],
            code,
            commit_message
        )

    except Exception as e:

        print(
            "GitHub Java upload error:",
            e
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


    # ========================================================
    # Commit README
    # ========================================================

    print(
        "Uploading README..."
    )

    try:

        create_github_file(
            problem["readme_path"],
            readme,
            f"Add README for {problem['number']}. {problem['title']}"
        )

    except Exception as e:

        print(
            "GitHub README upload error:",
            e
        )

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


    # ========================================================
    # Done
    # ========================================================

    print(
        "\n🎉 Successfully pushed to GitHub!"
    )

    return jsonify({

        "success": True,

        "folder": problem["folder"],

        "commit": commit_message,

        "submissionId": submission_id

    })


# ============================================================
# Server
# ============================================================

if __name__ == "__main__":

    print(
        "============================================"
    )

    print(
        "   LeetCode → GitHub Auto Sync Server"
    )

    print(
        "============================================"
    )

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8763
            )
        ),
        debug=False
    )
