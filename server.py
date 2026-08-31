from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import re
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

GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "LeetCodeProblems")

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"
GITHUB_API = "https://api.github.com"


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "success": True,
        "message": "LeetCode Auto Sync Server is running"
    })


# ============================================================
# GITHUB HELPERS
# ============================================================

def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def github_api_url(path):
    return f"{GITHUB_API}/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/{path}"


def check_github_config():
    missing = []

    if not GITHUB_USERNAME:
        missing.append("GITHUB_USERNAME")

    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")

    if not GITHUB_REPO:
        missing.append("GITHUB_REPO")

    return missing


# ============================================================
# TEST GITHUB CONNECTION
# ============================================================

@app.route("/github-test", methods=["GET"])
def github_test():

    missing = check_github_config()

    if missing:
        return jsonify({
            "success": False,
            "error": "Missing environment variables",
            "missing": missing
        }), 500

    try:
        response = requests.get(
            github_api_url(""),
            headers=github_headers(),
            timeout=15
        )

        if response.status_code == 200:
            repo_data = response.json()

            return jsonify({
                "success": True,
                "message": "GitHub connection successful",
                "repository": repo_data.get("full_name"),
                "private": repo_data.get("private")
            })

        return jsonify({
            "success": False,
            "error": "GitHub authentication/repository error",
            "status_code": response.status_code,
            "details": response.text
        }), response.status_code

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# LEETCODE GRAPHQL
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

    if not data.get("data") or not data["data"].get("question"):
        raise Exception("LeetCode question not found")

    return data["data"]["question"]


# ============================================================
# CREATE PROBLEM INFORMATION
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
# CHECK WHETHER FILE EXISTS ON GITHUB
# ============================================================

def github_file_exists(path):

    response = requests.get(
        github_api_url(f"contents/{path}"),
        headers=github_headers(),
        timeout=15
    )

    if response.status_code == 200:
        return True

    if response.status_code == 404:
        return False

    raise Exception(
        f"GitHub file check failed: "
        f"{response.status_code} {response.text}"
    )


# ============================================================
# CREATE / UPDATE FILE ON GITHUB
# ============================================================

def upload_file(path, content, commit_message):

    encoded_content = base64.b64encode(
        content.encode("utf-8")
    ).decode("utf-8")

    url = github_api_url(f"contents/{path}")

    # Check if file already exists
    response = requests.get(
        url,
        headers=github_headers(),
        timeout=15
    )

    sha = None

    if response.status_code == 200:
        sha = response.json().get("sha")

    elif response.status_code != 404:
        raise Exception(
            f"GitHub file check failed: "
            f"{response.status_code} {response.text}"
        )

    payload = {
        "message": commit_message,
        "content": encoded_content
    }

    # If file exists, GitHub requires its SHA for updating
    if sha:
        payload["sha"] = sha

    response = requests.put(
        url,
        headers=github_headers(),
        json=payload,
        timeout=20
    )

    if response.status_code not in [200, 201]:
        raise Exception(
            f"GitHub upload failed: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


# ============================================================
# OLD /SYNC ENDPOINT
# ============================================================

@app.route("/sync", methods=["POST"])
def sync():

    data = request.get_json()

    print("\n============================================")
    print("   LEETCODE SUBMISSION RECEIVED")
    print("============================================")

    if not data:
        return jsonify({
            "success": False,
            "error": "No JSON data received"
        }), 400

    print("Slug:", data.get("slug"))
    print("Language:", data.get("language"))
    print("Status:", data.get("status"))
    print("Runtime:", data.get("timeText"))
    print("Memory:", data.get("spaceText"))
    print("Submission ID:", data.get("submissionId"))

    return jsonify({
        "success": True,
        "message": "Submission received"
    })


# ============================================================
# SUBMISSION ENDPOINT
# ============================================================

@app.route("/submit", methods=["POST"])
def submit():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "error": "No JSON data received"
        }), 400

    print("\n============================================")
    print("       NEW LEETCODE SUBMISSION")
    print("============================================")

    print("Slug:", data.get("slug"))
    print("Status:", data.get("status"))
    print("Language:", data.get("language"))
    print("Runtime:", data.get("runtime"))
    print("Memory:", data.get("memory"))

    # ========================================================
    # CHECK GITHUB CONFIGURATION
    # ========================================================

    missing = check_github_config()

    if missing:
        print("Missing environment variables:", missing)

        return jsonify({
            "success": False,
            "error": "GitHub environment variables are missing",
            "missing": missing
        }), 500

    # ========================================================
    # ONLY ACCEPTED SUBMISSIONS
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
    # REQUIRED DATA
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

    if not slug:
        return jsonify({
            "success": False,
            "error": "Missing slug"
        }), 400

    if not code:
        return jsonify({
            "success": False,
            "error": "Missing code"
        }), 400

    # ========================================================
    # GET LEETCODE QUESTION
    # ========================================================

    try:

        print("\nFetching question from LeetCode...")

        question = fetch_question(slug)

        print(
            "Question:",
            question["questionFrontendId"],
            question["title"]
        )

    except Exception as e:

        print("LeetCode API error:", e)

        return jsonify({
            "success": False,
            "error": f"LeetCode API error: {str(e)}"
        }), 500

    # ========================================================
    # CREATE PROBLEM
    # ========================================================

    try:

        problem = create_problem(question)

    except Exception as e:

        print("Problem creation error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    print("\nFolder:", problem["folder"])
    print("Java file:", problem["java_path"])
    print("README:", problem["readme_path"])

    # ========================================================
    # CHECK FOR EXISTING SOLUTION
    # ========================================================

    try:

        if github_file_exists(problem["java_path"]):

            print("\nSolution already exists on GitHub.")

            return jsonify({
                "success": False,
                "error": "Solution already exists",
                "folder": problem["folder"]
            }), 409

    except Exception as e:

        print("GitHub file check error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    # ========================================================
    # CREATE README
    # ========================================================

    readme = (
        f'<h2><a href="https://leetcode.com/problems/'
        f'{problem["slug"]}">'
        f'{problem["number"]}. '
        f'{html.escape(problem["title"])}'
        f'</a></h2>'
        f'<h3>{problem["difficulty"]}</h3>'
        f'<hr>'
        f'{problem["content"]}\n'
    )

    # ========================================================
    # COMMIT MESSAGE
    # ========================================================

    commit_message = (
        f"Time: {runtime} "
        f"({runtime_percentile}), "
        f"Space: {memory} "
        f"({memory_percentile}) - "
        f"Satyam's leet extension"
    )

    print("\nCommit:")
    print(commit_message)

    # ========================================================
    # UPLOAD JAVA FILE
    # ========================================================

    try:

        print("\nUploading Java solution to GitHub...")

        java_result = upload_file(
            problem["java_path"],
            code,
            commit_message
        )

        print("Java solution uploaded successfully.")

    except Exception as e:

        print("Java upload error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    # ========================================================
    # UPLOAD README
    # ========================================================

    try:

        print("\nUploading README to GitHub...")

        readme_result = upload_file(
            problem["readme_path"],
            readme,
            commit_message
        )

        print("README uploaded successfully.")

    except Exception as e:

        print("README upload error:", e)

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    # ========================================================
    # SUCCESS
    # ========================================================

    print("\n============================================")
    print("       SUCCESSFULLY SYNCED TO GITHUB")
    print("============================================")

    return jsonify({
        "success": True,
        "message": "Solution successfully pushed to GitHub",
        "folder": problem["folder"],
        "javaFile": problem["java_path"],
        "readmeFile": problem["readme_path"],
        "commit": commit_message
    })


# ============================================================
# SERVER
# ============================================================

if __name__ == "__main__":

    print("============================================")
    print("   LeetCode → GitHub Auto Sync Server")
    print("============================================")

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        debug=False
    )
