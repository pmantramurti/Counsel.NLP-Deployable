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
                course_grade = tokens[-2]
                if course_grade in PASSING_GRADES:
                    courses[course_code] = [course_grade, curr_semester]
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
    transcript.drop(columns=['Description', 'Units', 'Grd Points', 'Repeat Code','Reqmnt Desig', 'Status'], inplace=True)
    transcript = transcript[transcript['Grade'].isna()]
    transcript.drop(columns=['Grade'], inplace=True)
    courses = [list(pair) for pair in zip(transcript['Course'], transcript['Term'])]
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
    output_string = "Note: User is only ready to graduate if there are no sections with remaining credits.\n"
    output_string += "Make sure to make separate recommendations for each possible specialization, if they exist.\n"
    output_string += "You only need to mention a section if it has remaining required credits.\n"
    output_string += "User Transcript: \n Major : " + student_major + " \n Current GPA : " + str(gpa_final) + "\n\n"
    #output_string += "They have taken :\n"
    #for course_code, (grade_earned, semester_taken) in courses.items():
    #    output_string += f"{semester_taken} - {course_code}: {grade_earned}\n"
    if final_recommendation["Type"] == "mult":
        for specialization in final_recommendation.keys():
            if specialization != "Type":
                output_string += "Remaining required credits for [" + specialization + "] specialization: \n"
                for category in final_recommendation[specialization].keys():
                    if isinstance(final_recommendation[specialization][category], dict):
                        for section in final_recommendation[specialization][category].keys():
                            if final_recommendation[specialization][category][section] != ["Requirement Met"]:
                                output_string += "\t" + section.replace("_",
                                                                        " ").title() + " section of " + category.replace(
                                    "_", " ").title() + ":" + str(
                                    needed_credits[specialization][category][section]) + " credits.\n"
                                output_string += "\t\t Course(s) user can take: "
                                #+ final_recommendation[specialization][category][section] + "\n")
                                #print(final_recommendation[specialization][category][section])
                                output_string += final_recommendation[specialization][category][section][0]
                                first = True
                                for course in final_recommendation[specialization][category][section]:
                                    if first:
                                        first = False
                                    else:
                                        output_string +=  ", " + course
                                output_string += "\n"
                    else:
                        if final_recommendation[specialization][category] != ["Requirement Met"]:
                            output_string += "\t" + category.replace("_", " ").title() + ":" + str(
                                needed_credits[specialization][category]) + " credits.\n"
                            output_string += "\t\t Course(s) user can take:"
                            output_string += final_recommendation[specialization][category][0]
                            first = True
                            for course in final_recommendation[specialization][category]:
                                if first:
                                    first = False
                                else:
                                    output_string += ", " + course
                            output_string += "\n"
    else:
        for category in final_recommendation.keys():
            if isinstance(final_recommendation[category], dict):
                for section in final_recommendation[category].keys():
                    if final_recommendation[category] != ["Requirement Met"]:
                        output_string += "\t" + section.replace("_", " ").title() + " section of " + category.replace(
                            "_", " ").title() + ": " + str(needed_credits[category][section]) + " credits.\n"
                        output_string += "\t\t Course(s) user can take:"
                        output_string += final_recommendation[category][0]
                        first = True
                        for course in final_recommendation[category]:
                            if first:
                                first = False
                            else:
                                output_string += ", " + course
                        output_string += "\n"
            else:
                if final_recommendation[category] != ["Requirement Met"]:
                    output_string += "\t" + category.replace("_", " ").title() + " category: " + str(
                        needed_credits[category]) + " credits.\n"
                    output_string += "\t\t Course(s) user can take:"
                    output_string += final_recommendation[category][0]
                    first = True
                    for course in final_recommendation[category]:
                        if first:
                            first = False
                        else:
                            output_string += ", " + course
                    output_string += "\n"
    courses_taken = list(courses.keys())
    output_string += "Courses taken: " + courses_taken[0]
    #print(courses)
    for course in courses_taken:
        if course is not courses_taken[0]:
            output_string += ', ' + course
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