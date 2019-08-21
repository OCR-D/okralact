from flask import render_template, redirect, url_for, request, send_file
from werkzeug.utils import secure_filename
from app import app, model_root, config_root, eval_root
from lib.file_operation import rename_file, get_model_dir
from rq.job import Job
import tarfile
import shutil
import os
from engines.validate_parameters import validate_string
import json
from lib.file_operation import list_model_dir
from app.lib.forms import *
from engines.common import read_help_information_html, read_model_param, read_list


def get_file_status():
    dict_status = {}
    for job_id in app.job_id2file:
        job = Job.fetch(job_id, app.redis)
        filename, config = app.job_id2file[job_id]
        dict_status[(filename, config)] = job.get_status()
    return dict_status

def get_valid_status():
    dict_status = {}
    for job_id in app.valid_id2file:
        job = Job.fetch(job_id, app.redis)
        filename, config = app.valid_id2file[job_id]
        dict_status[(filename, config)] = job.get_status()
    return dict_status


def get_eval_status():
    dict_status = {}
    for job_id in app.eval_id2file:
        job = Job.fetch(job_id, app.redis)
        trainname, testname, config = app.eval_id2file[job_id]
        print({'job': job, 'trainname': trainname, 'testname': testname, 'config': config})
        dict_status[(trainname, testname, config)] = job.get_status()
    return dict_status


# Manage Files
@app.route('/data', methods=['GET', 'POST'])
def manage_data():
    files_list = get_files()
    form = UploadDataForm()
    f = form.archive.data
    if form.validate_on_submit():
        filename = secure_filename(f.filename)
        prefix = '.'.join(filename.rsplit('.', 2)[:-2])
        filename = rename_file(prefix, '.tar.gz', files_list)
        f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return redirect(url_for('manage_data'))
    return render_template('data.html', form=form, files_list=files_list)


# Manage configure files
@app.route('/configs', methods=['GET', 'POST'], defaults={'error_message': ''})
@app.route('/configs/<error_message>', methods=['GET', 'POST'])
def manage_configs(error_message):
    configs_list = get_configs()
    form = UploadConfigForm()
    f = form.archive.data
    errors = error_message.split('\n')
    print(errors)
    print(error_message)
    if form.validate_on_submit():
        content = f.read()
        errors = validate_string(content)
        print(errors)
        if len(errors) > 0:
            print('print_error')
            return redirect(url_for('manage_configs', error_message='\n'.join(errors)))
        else:
            filename = secure_filename(f.filename)
            prefix = filename.rsplit('.')[0]
            filename = rename_file(prefix, '.json', configs_list)
            with open(os.path.join(app.config['CONFIG_FOLDER'], filename), 'w', encoding='utf-8') as f_:
                json.dump(json.loads(content.decode('ascii')), f_)
            return redirect(url_for('manage_configs'))
    return render_template('configs.html', errors=errors, form=form, files_list=configs_list)


@app.route('/delete_data/<filename>')
def delete_data(filename):
    if filename in app.job_file2id:
        app.job_file2id.pop(filename, None)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    os.remove(file_path)
    prefix = filename.rsplit('.', 2)[0]
    model_file = os.path.join(os.getcwd(), 'engines/model', 'model_%s' % filename)
    if os.path.exists(model_file):
        os.remove(model_file)
    model_folder = os.path.join(os.getcwd(), 'engines/model', prefix)
    if os.path.exists(model_folder):
        shutil.rmtree(model_folder, ignore_errors=True)
    return redirect(url_for('manage_data'))


@app.route('/delete_config/<filename>')
def delete_config(filename):
    if filename in app.job_file2id:
        app.job_file2id.pop(filename, None)
    file_path = os.path.join(app.config['CONFIG_FOLDER'], filename)
    os.remove(file_path)
    return redirect(url_for('manage_configs'))


# Manage jobs
@app.route('/jobs', methods=['GET', 'POST'], defaults={'error_message': ''})
@app.route('/jobs/<error_message>', methods=['GET', 'POST'])
def manage_job(error_message):
    print('validation error', error_message)
    dict_status = get_file_status()
    dict_valid_status = get_valid_status()
    print(app.job_file2id)
    print(dict_status)
    form = SelectConfigForm()
    if request.method == 'POST':
        print("form:", request.form)
        data_choices = dict(get_options(get_files()))
        config_choices = dict(get_options(get_configs()))
        print(get_configs())
        select_config = config_choices.get(form.select_config.data)
        select_data = data_choices.get(form.select_data.data)
        print('data', select_data)
        print('config:', select_config)
        if form.submit.data:
            return redirect(url_for('train_model', filename=select_data, config=select_config))
        elif form.submit_valid.data:
            return redirect(url_for('valid_model', filename=select_data, config=select_config))
    return render_template('jobs.html', form=form, dict_status=dict_status, dict_valid_status=dict_valid_status, errors = error_message)


# Manage Models
@app.route('/models', methods=['GET', 'POST'])
def manage_model():
    model_dict = list_model_dir()
    return render_template('models.html', dict_model=model_dict)


# Manage Model files
@app.route('/models/<model_dir>', methods=['GET', 'POST'])
def manage_model_list(model_dir):
    tess_path = os.path.join(model_root, model_dir, "checkpoint")
    if os.path.exists(tess_path) and os.path.isdir(tess_path):
        models = [ele for ele in os.listdir(tess_path)]
    else:
        models = [ele for ele in os.listdir(os.path.join(model_root, model_dir))]
    print("models:\n", models)
    file_list = []
    for ele in models:
        if ele.endswith('mlmodel') or ele.endswith('.pyrnn.gz') or ele.endswith("checkpoint"):
            file_list.append(ele)
        elif ".ckpt." in ele and ele != "checkpoint":
            file_list.append(ele)
    if os.path.exists(os.path.join(model_root, model_dir, "report")):
        file_list.append("report")
    print(file_list)
    return render_template('model_list.html',  model_dir=model_dir, files_list=file_list)


# Manage Evals
@app.route('/evaluation', methods=['GET', 'POST'])
def manage_eval():
    dict_status = get_eval_status()
    print(app.eval_file2id)
    print(dict_status)
    form = SelectModelForm()
    if request.method == 'POST':
        train_choices = dict(get_options(get_files()))
        test_choices = dict(get_options(get_files()))
        config_choices = dict(get_options(get_configs()))
        print(get_configs())
        select_config = config_choices.get(form.select_config.data)
        select_test = test_choices.get(form.select_test.data)
        select_train = train_choices.get(form.select_train.data)
        print('train', select_train)
        print('test', select_test)
        print('config:', select_config)
        return redirect(url_for('eval_model', testname=select_test, trainname=select_train, config=select_config))
    return render_template('eval.html', form=form, dict_status=dict_status)


# Run jobs
@app.route('/run', methods=['POST', 'GET'])
def train_model():
    print('train_model')
    filename = request.args.get('filename', None)
    config = request.args.get('config', None)
    print(filename, config)
    # form = SelectConfigForm()
    if (filename, config) not in app.job_file2id:
        job = app.task_queue.enqueue('engines.train.train_from_file', filename, config)
        job_id = job.get_id()
        app.job_file2id[(filename, config)] = job_id
        app.job_id2file[job_id] = (filename, config)
    print(app.job_id2file)
    # files_list = os.listdir(app.config['UPLOAD_FOLDER'])
    return redirect(url_for('manage_job'))


# Run jobs
@app.route('/eval', methods=['POST', 'GET'])
def eval_model():
    print('train_model')
    trainname = request.args.get('trainname', None)
    testname = request.args.get('testname', None)
    config = request.args.get('config', None)
    print(trainname, testname, config)
    if (testname, trainname, config) not in app.eval_file2id:
        job = app.eval_queue.enqueue('engines.eval.eval_from_file', testname, trainname, config)
        job_id = job.get_id()
        app.eval_file2id[(testname, trainname, config)] = job_id
        app.eval_id2file[job_id] = (testname, trainname, config)
    print(app.eval_id2file)
    return redirect(url_for('manage_eval'))

# # Run jobs
@app.route('/valid', methods=['POST', 'GET'])
def valid_model():
    print('valid_model')
    trainset = request.args.get('filename', None)
    config = request.args.get('config', None)
    print(trainset, config)
    if (trainset, config) not in app.job_file2id:
        return redirect(url_for('manage_job', error_message='Please train the model first.'))
    else:
        job_id = app.job_file2id[(trainset, config)]
        job = Job.fetch(job_id, app.redis)
        status = job.get_status()
        print('status', status)
        if status == 'queued':  # Not start training yet
            return redirect(url_for('manage_job', error_message='Job has not started yet'))
        elif status == 'failed': # Training job failed
            return redirect(url_for('manage_job', error_message='Job Failed'))
        else:
            if (trainset, config) not in app.valid_file2id:
                job = app.valid_queue.enqueue('engines.valid.valid_from_file', trainset, config)
                job_id = job.get_id()
                app.valid_file2id[(trainset, config)] = job_id
                app.valid_id2file[job_id] = (trainset, config)
                print(app.valid_id2file)
                return redirect(url_for('manage_job'))
            else:
                job_id = app.valid_file2id[(trainset, config)]
                job = Job.fetch(job_id, app.redis)
                status = job.get_status()
                print('valid_status', status)
                if status == 'queued':
                    return redirect(url_for('manage_job', error_message='Validation job already in queue'))
                else:
                    job = app.valid_queue.enqueue('engines.valid.valid_from_file', trainset, config)
                    job_id = job.get_id()
                    app.valid_file2id[(trainset, config)] = job_id
                    app.valid_id2file[job_id] = (trainset, config)
                    print(app.valid_id2file)
                    return redirect(url_for('manage_job'))

def tardir(path, tar_name):
    with tarfile.open(tar_name, "w:gz") as tar_handle:
        for root, dirs, files in os.walk(path):
            for file in files:
                tar_handle.add(os.path.join(root, file))


@app.route('/download/', methods=['GET', 'POST'])
def download():
    model_dir = request.args.get('model_dir', None)
    file_name = request.args.get("filename", None)
    out_file = os.path.join(os.getcwd(), model_root, model_dir, file_name)
    return send_file(out_file, attachment_filename=file_name, as_attachment=True)


@app.route('/show_file', methods=['GET', 'POST'])
def show_content():
    file_name = request.args.get("filename", None)
    file_type = request.args.get("type", None)
    data_dir = request.args.get("file_dir", None)
    print(file_name, file_type, data_dir)
    if file_type == "config":
        text = open(os.path.join(config_root, file_name), 'r', encoding="utf-8")
        content = text.read()
        text.close()
    elif file_type == "report":
        text = open(os.path.join(model_root, data_dir, file_name), 'r', encoding="utf-8")
        content = text.read()
        text.close()
    elif file_type == 'eval':
        with open(os.path.join(eval_root, file_name), 'r', encoding="utf-8") as f_:
            res = json.loads(f_.read())
        content = '\n'
        for ele in res:
            content += ele + '\t' + str(res[ele]) + '\n'
    return render_template('content.html', response=content)

@app.route('/show_report', methods=['GET', 'POST'])
def show_report():
    trainset = request.args.get("filename", None)
    config = request.args.get("config", None)
    model_dir = get_model_dir(trainset, config)
    filename = 'report'
    print(trainset, config, model_dir)
    text = open(os.path.join(os.getcwd(), model_root, model_dir, filename), 'r', encoding="utf-8")
    content = text.read()
    text.close()
    return render_template('content.html', response=content)

# Manual of Using OCR Engines
@app.route('/', methods=['GET', 'POST'], defaults={'engine': 'kraken'})
@app.route('/<engine>',  methods=['GET', 'POST'])
def manual(engine):
    print(engine)
    help_info = read_help_information_html(engine)
    form = SelectEngineForm()
    if request.method == 'POST':
        engine_choices = dict(get_options(get_engines()))
        select_engine = engine_choices.get(form.select_engine.data)
        print('engine', select_engine)
        return redirect(url_for('manual', engine=select_engine))
    return render_template('manual.html', form=form, engine=engine, help_info=help_info)


# Model info
@app.route('/manual_model',  methods=['GET', 'POST'])
def get_model_info():
    print('train_model')
    engine = request.args.get('engine_name', None)
    print("current engine", engine)
    help_info = read_model_param(engine)
    return render_template('model.html', engine=engine, help_info=help_info)


@app.route("/results", methods=['GET'])
def get_results():
    testname = request.args.get('testname', None)
    configname = request.args.get('configname', None)
    trainname = request.args.get('trainname', None)
    dict_eval = read_list('static/eval/eval_list')
    key = (testname, trainname, configname)
    res_file = dict_eval[key]
    return redirect(url_for('show_content', filename=res_file, file_dir='', type='eval'))
