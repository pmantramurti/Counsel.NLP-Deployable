import copy
import pandas as pd
import os
import json

PASSING_GRADES = ["CR", "C-", "C", "C+", "B-", "B", "B+", "A-", "A", "A+"]


def parse_transcript(transcript_contents, valid_courses):
    lines = transcript_contents.splitlines()
    major_name = None
    courses = {}
    gpa = 0
    course_set = set(valid_courses)
    semester_gpa = {}
    curr_semester = ""

    for line in lines:
        if "MAJOR:" in line:
            major_name = line.split("MAJOR:")[1].strip()
        if "SEMESTER" in line and "TOTAL" not in line:
            curr_semester = line.strip().replace("SEMESTER ", "").replace("  ", " ").title()
        tokens = line.strip().replace("  ", " ").split()
        if len(tokens) >= 2:
            course_code = " ".join(tokens[:2])
            if course_code in course_set:
                # Extract course name
                course_name_tokens = []
                for token in tokens[2:]:
                    if token.replace('.', '', 1).isdigit():
                        break
                    course_name_tokens.append(token)
                course_name = ' '.join(course_name_tokens)

                course_grade = tokens[-2]
                if course_grade in PASSING_GRADES:
                    courses[course_code] = [course_grade, curr_semester, course_name]
            elif course_code == "SEMESTER TOTAL:":
                semester_gpa[curr_semester] = tokens[-1]
            elif course_code == "ALL COLLEGE:":
                gpa = tokens[-1]

    return major_name, courses, semester_gpa, gpa

def parse_course_list(file):
    try:
        # Try reading as HTML table (used in transcript export from web)
        transcript = pd.read_html(file, header=None)[0]
    except ValueError:
        # If no tables found, fallback to reading as Excel
        transcript = pd.read_excel(file, header=None)
    print(transcript)
    transcript.drop(columns=['Units', 'Grd Points', 'Repeat Code','Reqmnt Desig', 'Status'], inplace=True)
    transcript = transcript[transcript['Grade'].isna()]
    transcript.drop(columns=['Grade'], inplace=True)
    courses = [list(pair) for pair in zip(transcript['Course'], transcript['Term'], transcript['Description'])]
    return courses

def course_recommendation(transcript_courses, student_major):
    if student_major == "MS Artificial Intelligence":
        major_file = "msai_dataset.json"
    elif student_major == "MS Computer Engineering":
        major_file = "mscmpe_dataset.json"
    elif student_major == "MS Computer Science":
        major_file = "mscs_dataset.json"
    elif student_major == "MS Software Engineering":
        major_file = "msse_dataset.json"
    else:
        return
    with open(major_file, "r") as f:
        major_data = json.load(f)[0]
    major_struct = major_data["unit_distribution"]
    final_recommendation = {}
    credits_required = {}
    if "specialization_tracks" in major_struct:
        for specialization in major_data["specialization_tracks"].keys():
            final_recommendation[specialization], credits_required[specialization] = process_transcript(transcript_courses, major_data, major_struct, specialization)
        final_recommendation["Type"] = "mult"
    else:
        final_recommendation, credits_required = process_transcript(transcript_courses, major_data, major_struct)
        final_recommendation["Type"] = "single"

    return final_recommendation, credits_required

def display_recommendation(courses, final_recommendation, needed_credits, gpa_final, student_major):
    output_string = (
        "The courses listed below are the only courses that are still required for the degree.\n"
        "If there are no courses recommended below, the user is fully ready to graduate.\n"
        "Separate recommendations are made for each specialization, if they exist.\n"
        "When recommending courses for an upcoming semester, recommend up to 4 courses from those listed below by this order of priority:\n"
        "Core Courses, Specialization, Electives, Writing Credit, Culminating Experience\n"
        "Skip the listed categories that are not mentioned below.\n"
        "Culminating Experience courses can only be recommended if the rest of the listed courses number less than 4.\n"
        "The following details can be treated as the user's transcript:\n"
        f"User Transcript:\n Major: {student_major}\n Current GPA: {gpa_final}\n\n"
    )

    recommendations_found = False  # Track if any recommendations exist

    if final_recommendation.get("Type") == "mult":
        for specialization, spec_data in final_recommendation.items():
            if specialization == "Type":
                continue

            spec_output = f"Remaining required credits for [{specialization}] specialization:\n"
            spec_has_recs = False

            for category, cat_data in spec_data.items():
                if isinstance(cat_data, dict):  # Has sections
                    for section, courses_list in cat_data.items():
                        if courses_list != ["Requirement Met"]:
                            credits = needed_credits[specialization][category][section]
                            course_options = ", ".join(
                                [item if isinstance(item, str) else item[0] for item in courses_list]
                            )
                            spec_output += (
                                f"\t{section.replace('_', ' ').title()} section of {category.replace('_', ' ').title()} still requires: "
                                f"{credits} credits.\n"
                                f"\t\tCourses you can take: {course_options}\n"
                            )
                            spec_has_recs = True
                else:
                    if cat_data != ["Requirement Met"]:
                        credits = needed_credits[specialization][category]
                        course_options = ", ".join(cat_data)
                        spec_output += (
                            f"\t{category.replace('_', ' ').title()} still requires: {credits} credits.\n"
                            f"\t\tCourses you can take: {course_options}\n"
                        )
                        spec_has_recs = True

            if spec_has_recs:
                output_string += spec_output + "\n"
                recommendations_found = True
            else:
                output_string += f"The [{specialization}] specialization has no remaining requirements. The user is ready to graduate for this specialization.\n\n"

    else:
        # Single specialization case
        single_output = ""
        single_has_recs = False

        for category, cat_data in final_recommendation.items():
            if isinstance(cat_data, dict):  # Has sections
                for section, courses_list in cat_data.items():
                    if courses_list != ["Requirement Met"]:
                        credits = needed_credits[category][section]
                        course_options = ", ".join(courses_list)
                        single_output += (
                            f"\t{section.replace('_', ' ').title()} section of {category.replace('_', ' ').title()} still requires: "
                            f"{credits} credits.\n"
                            f"\t\tCourses you can take: {course_options}\n"
                        )
                        single_has_recs = True
            else:
                if cat_data != ["Requirement Met"]:
                    credits = needed_credits[category]
                    course_options = ", ".join(cat_data)
                    single_output += (
                        f"\t{category.replace('_', ' ').title()} category still requires: {credits} credits.\n"
                        f"\t\tCourses you can take: {course_options}\n"
                    )
                    single_has_recs = True

        if single_has_recs:
            output_string += single_output + "\n"
            recommendations_found = True
        else:
            output_string += "There are no remaining requirements. The user is ready to graduate.\n\n"

    # Final catch: if absolutely no recommendations were found (empty input case)
    if not recommendations_found:
        output_string += "\nNo remaining required courses were found. The user is fully ready to graduate.\n"

    return output_string


def process_transcript(transcript, major_data, major_struct, specialization = None):
    transcript_courses = copy.deepcopy(transcript)
    recommended_courses = {}
    credits_required = {}
    for category, requirement in major_struct.items():
        # int in struct and array in overall = take at least int credits worth of courses in array
        if isinstance(requirement, int) and isinstance(major_data[category], list):
            course_options_temp = [[listing["course"], listing["units"]] for listing in major_data[category]]
            course_options = [[listing["course"], listing["units"]] for listing in major_data[category]]
            credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
            if credits_taken < requirement:
                recommended_courses[category] = [c[0] for c in course_options]
                credits_required[category] = requirement - credits_taken
            else:
                recommended_courses[category] = ["Requirement Met"]
                credits_required[category] = 0

        if isinstance(requirement, int) and isinstance(major_data[category], dict) and category != "culminating_experience":
            # print(major_data[category])
            course_options_temp = [[listing["course"], listing["units"]] for listing in major_data[category][specialization]]
            course_options = [[listing["course"], listing["units"]] for listing in major_data[category][specialization]]
            credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
            if credits_taken < requirement:
                recommended_courses[category] = [c[0] for c in course_options]
                credits_required[category] = requirement - credits_taken
            else:
                recommended_courses[category] = ["Requirement Met"]
                credits_required[category] = 0

        if isinstance(requirement, int) and isinstance(major_data[category], dict) and category == "culminating_experience":
            temp_dict = {}
            temp_cred = {}
            for exp_type in major_data[category].keys():
                # print(exp_type)
                course_options_temp = [[listing["course"], listing["units"]] for listing in major_data[category][exp_type]]
                course_options = [[listing["course"], listing["units"]] for listing in major_data[category][exp_type]]
                credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
                if credits_taken < requirement:
                    temp_dict[exp_type] = [c[0] for c in course_options]
                    temp_cred[exp_type] = requirement - credits_taken
                else:
                    temp_dict[exp_type] = ["Requirement Met"]
                    temp_cred[exp_type] = 0
            if (temp_cred[list(temp_cred)[0]] and temp_cred[list(temp_cred)[0]] < requirement) or not temp_cred[list(temp_cred)[0]]:
                recommended_courses[category] = {list(temp_dict)[0]:temp_dict[list(temp_dict)[0]]}
                credits_required[category] = {list(temp_cred)[0]:temp_cred[list(temp_cred)[0]]}
            elif (temp_cred[list(temp_cred)[1]] and temp_cred[list(temp_cred)[1]] < requirement) or not temp_cred[list(temp_cred)[1]]:
                recommended_courses[category] = {list(temp_dict)[1]:temp_dict[list(temp_dict)[1]]}
                credits_required[category] = {list(temp_cred)[1]:temp_cred[list(temp_cred)[1]]}
            else:
                recommended_courses[category] = temp_dict
                credits_required[category] = temp_cred

        # dictionary of ints in struct and dictionary of arrays in overall = take at least int in each section of courses until reach required "total" credits
        # - two versions,
        #  -- one where sections = categories, ie mscs, and credits needed from all categories - mode = "cumulative"
        #  -- one where sections = parts of specializations, ie msse, credits needed from one category - mode = "per group"
        if isinstance(requirement, dict):
            temp_dict = {}
            temp_cred = {}
            sum_total = requirement["Total"]
            requirement_sections = {cat:cont for cat, cont in requirement.items() if cat != "Total"}
            #print(requirement)
            #next(iter(my_dict.values()))
            if isinstance(next(iter(requirement_sections.values())), int) and isinstance(major_data[category][0], dict):
                specialization_course_list = major_data[category][specialization]
                for cat, cont in requirement_sections.items():
                    course_options_temp = [[listing["course"], listing["units"]] for listing in specialization_course_list[cat]]
                    course_options = [[listing["course"], listing["units"]] for listing in specialization_course_list[cat]]
                    credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
                    if credits_taken < cont:
                        temp_dict[cat] = [c[0] for c in course_options]
                        temp_cred[cat] = cont - credits_taken
                    else:
                        temp_dict[cat] = ["Requirement Met"]
                        temp_cred[cat] = 0
            if isinstance(next(iter(requirement_sections.values())), int) and isinstance(major_data[category][0], list):
                for cat, cont in requirement_sections.items():
                    course_options_temp = [[listing["course"], listing["units"]] for listing in major_data[category][cat]]
                    course_options = [[listing["course"], listing["units"]] for listing in major_data[category][cat]]
                    credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
                    if credits_taken < cont:
                        temp_dict[cat] = [c[0] for c in course_options]
                        temp_cred[cat] = cont - credits_taken
                    else:
                        temp_dict[cat] = ["Requirement Met"]
                        temp_cred[cat] = 0

            # dictionary of arrays in struct and dictionary of arrays in overall = take array[0] to array[1] for each section in overall until reach total
            if isinstance(next(iter(requirement_sections.values())), list):
                creds_filled = 0
                all_course_options = []
                for cat, cont in requirement_sections.items():
                    min_cred = cont[0]
                    course_options_temp = [[listing["course"], listing["units"]] for listing in
                                           major_data[category][cat]]
                    course_options = [[listing["course"], listing["units"]] for listing in major_data[category][cat]]
                    credits_taken, course_options, transcript_courses = check_courses(course_options, transcript_courses, course_options_temp)
                    # diff = [item for item in course_options_temp if item not in course_options]
                    # print(diff)
                    if credits_taken < min_cred:
                        temp_dict[cat] = [c[0] for c in course_options]
                        temp_cred[cat] = min_cred - credits_taken
                    else:
                        temp_dict[cat] = ["Requirement Met"]
                        temp_cred[cat] = 0
                    all_course_options += course_options
                    creds_filled += credits_taken
                if creds_filled < sum_total:
                    temp_dict[category] = all_course_options
                    temp_cred[category] = sum_total - creds_filled

            recommended_courses[category] = temp_dict
            credits_required[category] = temp_cred


    return recommended_courses, credits_required

def check_courses(course_options, transcript_courses, course_options_temp):
    credits_taken = 0
    for c in course_options_temp:
        if c[0] in transcript_courses.keys():
            credits_taken += c[1]
            course_options.remove(c)
            del transcript_courses[c[0]]

    return credits_taken, course_options, transcript_courses

#with open("courses.txt", "r") as f:
#    course_list = f.read().splitlines()

# Load the uploaded transcript file
#with open("Jeffrey_Info/transcript.txt", "r", encoding="utf-8") as f:
#    contents = f.read()

#ps_file = "Jeffrey_Info/ps.xls"
#skip = False

#major, courses_taken, gpa_per_sem, curr_gpa = parse_transcript(contents, course_list)
#if not skip and os.path.exists(ps_file):
#    current_courses = parse_course_list(ps_file)
#    for course, semester in current_courses:
#        courses_taken[course] = ["In Progress", semester]

#print("Major:", major)
#print("Courses Taken:")
#for course, (grade, semester) in courses_taken.items():
#    print(f"{semester} - {course}: {grade}")
#print()
#print("Semester GPA:")
#for semester, gpa_sem in gpa_per_sem.items():
#    print(f"{semester} - {gpa_sem}")
#print()
#print("Current GPA: " + curr_gpa)
#print()

#course_rec, cred_req = course_recommendation(courses_taken, major)
#print(display_recommendation(courses_taken, course_rec, cred_req, curr_gpa, major))
