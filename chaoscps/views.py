from django.contrib.auth import logout
from django.shortcuts import redirect, render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.template.loader import render_to_string
from chaos.models import Version, Hypothesis, Experiment, Execution, SteadyState, Element, Evaluation, Recovery
import datetime
import json
import io
import re
from django.views.decorators.csrf import csrf_exempt

def custom_logout(request):
    logout(request)
    return redirect('/admin/login/')

def home(request):
    return redirect('/admin/')

@login_required(login_url='/admin/login/')
def version_report(request, version_uuid):
    """
    Generate a comprehensive report for a specific version
    """
    # Get the version object - check ownership if not superuser
    if request.user.is_superuser:
        version = get_object_or_404(Version, uuid=version_uuid)
    else:
        version = get_object_or_404(Version, uuid=version_uuid, created_by=request.user)

    # Get all related objects - filter by ownership if not superuser
    if request.user.is_superuser:
        hypotheses = Hypothesis.objects.filter(version=version)
        elements = Element.objects.filter(version=version, parent=None)  # Top-level elements only
        steady_states = SteadyState.objects.filter(version=version)
        # Get all experiments related to this version's hypotheses
        experiments = Experiment.objects.filter(hypothesis__in=hypotheses)
    else:
        hypotheses = Hypothesis.objects.filter(version=version, created_by=request.user)
        elements = Element.objects.filter(version=version, parent=None, created_by=request.user)  # Top-level elements only
        steady_states = SteadyState.objects.filter(version=version, created_by=request.user)
        # Get all experiments related to this version's hypotheses
        experiments = Experiment.objects.filter(hypothesis__in=hypotheses, created_by=request.user)

    # Get all executions for these experiments - filter by experiment ownership
    executions = Execution.objects.filter(experiment__in=experiments)
    evaluations = Evaluation.objects.filter(execution__in=executions)
    recoveries = Recovery.objects.filter(execution__in=executions)
    
    # Calculate pass rate
    total_evaluations = Evaluation.objects.filter(execution__in=executions).count()
    if total_evaluations > 0:
        passing_evaluations = Evaluation.objects.filter(
            execution__in=executions, 
            status='pass'
        ).count()
        pass_rate = round((passing_evaluations / total_evaluations) * 100)
    else:
        pass_rate = 0

    fail_rate = 100 - pass_rate
    
    context = {
        'version': version,
        'hypotheses': hypotheses,
        'elements': elements,
        'steady_states': steady_states,
        'experiments': experiments,
        'executions': executions,
        'evaluations': evaluations,
        'recoveries': recoveries,
        'pass_rate': pass_rate,
        'fail_rate': fail_rate,
        'generated_date': datetime.datetime.now(),
    }
    
    return render(request, 'chaos/report_detail.html', context)

def get_version_details_text(request, version_uuid):
    """
    Get comprehensive version details and SUT information as a single text for webhook submission
    Returns all elements, steady states, hypotheses, and experiments separately in JSON response
    """

    try:
        # Get the version object
        version = get_object_or_404(Version, uuid=version_uuid)
        # Get elements created by the same user who created the version
        elements = Element.objects.filter(version=version, created_by=version.created_by)  # All elements regardless of parent
        # Get steady states created by the same user who created the version
        steady_states = SteadyState.objects.filter(version=version, created_by=version.created_by)
        # Get hypotheses created by the same user who created the version
        hypotheses = Hypothesis.objects.filter(version=version, created_by=version.created_by)
        # Get experiments related to these hypotheses
        experiments = Experiment.objects.filter(hypothesis__in=hypotheses, created_by=version.created_by)
        
        # Build comprehensive text report
        report_text = []
        summary_text = []

        # Combined Customer, SUT and Version Information
        report_text.append("=== SYSTEM UNDER TEST (SUT) ===")
        report_text.append(f"Customer: {version.sut.customer.name}")
        summary_text.append(f"Customer: {version.sut.customer.name}")
        if version.sut.customer.description:
            report_text.append(f"Customer Description: {version.sut.customer.description}")
        report_text.append(f"SUT Name: {version.sut.name}")
        summary_text.append(f"SUT Name: {version.sut.name}")
        if version.sut.description:
            report_text.append(f"SUT Description: {version.sut.description}")
        report_text.append(f"SUT Version Name: {version.name}")
        summary_text.append(f"SUT Version Name: {version.name}")
        if version.description != version.sut.description:
            report_text.append(f"SUT Version Description: {version.description}")
        if version.notes:
            report_text.append(f"**IMPORTANT CONTEXT INFORMATION TO CONSIDER WHEN GENERATING COMPONENTS, STEADY STATES, HYPOTHESES AND EXPERIMENTS FOR THIS VERSION OF THE SUT** : \n{version.notes}")
        report_text.append("")
        
        # Generate final single text
        final_text = "\n".join(report_text)
        final_summary_text = " - ".join(summary_text)
        # Serialize elements
        elements_data = []
        if elements.exists():
            for element in elements:
                element_dict = {
                    #'uuid': str(element.uuid),
                    'name': element.name,
                    'description': element.description or '',
                    #'dependencies': element.dependencies or '',
                    #'justification': element.justification or '',
                    'parent': element.parent.name if element.parent else None,
                    #'parent_uuid': str(element.parent.uuid) if element.parent else None,
                }
                elements_data.append(element_dict)
        
        # Serialize steady states
        steady_states_data = []
        if steady_states.exists():
            for steady_state in steady_states:
                steady_state_dict = {
                    #'uuid': str(steady_state.uuid),
                    'metric_name': steady_state.metric_name,
                    #'category': steady_state.category or '',
                    'normal_behavior': steady_state.normal_behavior or '',
                    'deviation_indicators': steady_state.deviation_indicators or '',
                    #'justification': steady_state.justification or '',
                }
                steady_states_data.append(steady_state_dict)
        
        # Serialize hypotheses
        hypotheses_data = []
        if hypotheses.exists():
            for hypothesis in hypotheses:
                hypothesis_dict = {
                    #'uuid': str(hypothesis.uuid),
                    'name': hypothesis.name,
                    'description': hypothesis.description or '',
                    #'justification': hypothesis.justification or '',
                    #'elements': [{'uuid': str(e.uuid), 'name': e.name} for e in hypothesis.elements.all()],
                    #'steady_states': [{#'uuid': str(ss.uuid), 'metric_name': ss.metric_name} for ss in hypothesis.steady_states.all()],
                }
                hypotheses_data.append(hypothesis_dict)
        
        # Serialize experiments
        experiments_data = []
        if experiments.exists():
            for experiment in experiments:
                # Extract first two sentences from description
                description_text = ''
                if experiment.description:
                    desc = experiment.description.strip()
                    if desc:
                        # Split by period followed by one or more spaces
                        sentences = re.split(r'\.\s+', desc)
                        # Filter out empty strings and strip whitespace
                        sentences = [s.strip() for s in sentences if s.strip()]
                        
                        if len(sentences) >= 2:
                            # Two or more sentences: join first two with period and space
                            description_text = '. '.join(sentences[:2]) + '.'
                        elif len(sentences) == 1:
                            # Only one sentence - check if it ends with period
                            # (if original had period+space, it was split; if period at end, it wasn't)
                            description_text = sentences[0]
                            # If original text ends with period (without space), preserve it
                            if desc.rstrip().endswith('.') and not description_text.endswith('.'):
                                description_text += '.'
                        else:
                            # No periods with spaces found - return original text as-is
                            description_text = desc
                
                experiment_dict = {
                    #'uuid': str(experiment.uuid),
                    'name': experiment.name,
                    'description': description_text,
                    #'justification': experiment.justification or '',
                    'hypothesis': {
                        #'uuid': str(experiment.hypothesis.uuid),
                        'name': experiment.hypothesis.name,
                    },
                    'elements': [{#'uuid': str(e.uuid), 
                        'name': e.name} for e in experiment.elements.all()],
                    'steady_states': [{#'uuid': str(ss.uuid), 
                        'metric_name': ss.metric_name} for ss in experiment.steady_states.all()],
                }
                experiments_data.append(experiment_dict)
        
        return JsonResponse({
            'success': True,
            'version_uuid': str(version_uuid),
            'text_report': final_text,
            'summary_text': final_summary_text,
            'elements': json.dumps(elements_data),
            'steady_states': json.dumps(steady_states_data),
            'hypotheses': json.dumps(hypotheses_data),
            'experiments': json.dumps(experiments_data),
            'generated_date': datetime.datetime.now().isoformat()
        })
        
    except Version.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Version with UUID {version_uuid} not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'An error occurred: {str(e)}'}, status=500)

@csrf_exempt
def save_version_data(request, version_uuid):
    """
    Save or update components, steady states, hypotheses, and experiments from JSON data.
    Can save one or more of: 'componentJson', 'steadyStateJson', 'hypothesisJson', 'experimentJson'
    At least one section must be provided.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method is allowed'}, status=405)

    try:
        # Get the version object
        version = get_object_or_404(Version, uuid=version_uuid)
        
        # Parse JSON data
        try:
            raw_data = json.loads(request.body)
            # Handle both array and single object formats
            if isinstance(raw_data, list) and len(raw_data) > 0:
                data = raw_data[0]  # Take the first object from the array
            else:
                data = raw_data
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
        
        # Validate that at least one section is provided
        valid_sections = ['componentJson', 'steadyStateJson', 'hypothesisJson', 'experimentJson']
        provided_sections = [section for section in valid_sections if section in data]
        
        if not provided_sections:
            return JsonResponse({
                'success': False, 
                'error': 'At least one section must be provided. Valid sections: componentJson, steadyStateJson, hypothesisJson, experimentJson'
            }, status=400)
        
        # Validate structure of each provided section
        section_structure = {
            'componentJson': 'components',
            'steadyStateJson': 'steady_state_metrics',
            'hypothesisJson': 'hypotheses',
            'experimentJson': 'experiments'
        }
        
        for section in provided_sections:
            if not isinstance(data[section], dict):
                # NEW: If it's a list/array, auto-wrap it in the expected structure
                if isinstance(data[section], list):
                    expected_key = section_structure[section]
                    data[section] = {expected_key: data[section]}
                else:
                    return JsonResponse({
                        'success': False,
                        'error': f'Section "{section}" must be a JSON object (dictionary) or array'
                    }, status=400)
            
            # If section is not empty, validate it has the expected key
            if data[section]:  # Not empty
                expected_key = section_structure[section]
                if expected_key not in data[section]:
                    return JsonResponse({
                        'success': False,
                        'error': f'Section "{section}" must contain a "{expected_key}" key'
                    }, status=400)
                
                if not isinstance(data[section][expected_key], list):
                    return JsonResponse({
                        'success': False,
                        'error': f'Section "{section}" must have "{expected_key}" as a list/array'
                    }, status=400)
        
        # Initialize response data
        response_data = {
            'success': True,
            'version_uuid': str(version_uuid),
            'created': {'elements': 0, 'steady_states': 0, 'hypotheses': 0, 'experiments': 0},
            'updated': {'elements': 0, 'steady_states': 0, 'hypotheses': 0, 'experiments': 0},
            'errors': []
        }
        
        # Process Components (Elements)
        if 'componentJson' in data and 'components' in data['componentJson']:
            for component_data in data['componentJson']['components']:
                try:
                    component_name = component_data.get('Component Name')
                    if not component_name:
                        response_data['errors'].append('Component missing Component Name')
                        continue
                    
                    # Handle parent component
                    parent_component_name = component_data.get('Parent Component')
                    parent_element = None
                    if parent_component_name and parent_component_name.lower() != 'none':
                        try:
                            parent_element = Element.objects.get(version=version, name=parent_component_name)
                        except Element.DoesNotExist:
                            response_data['errors'].append(f'Parent component "{parent_component_name}" not found for component {component_name}')
                            #continue
                    
                    # Convert dependencies list to string
                    dependencies_list = component_data.get('Dependencies', [])
                    dependencies_str = ', '.join(dependencies_list) if dependencies_list else ''
                    
                    # Check if element exists by name in this version
                    element, created = Element.objects.get_or_create(
                        version=version,
                        name=component_name,
                        defaults={
                            'description': component_data.get('Description', '').replace('**', ''),
                            'dependencies': dependencies_str,
                            'justification': component_data.get('Justification', ''),
                            'parent': parent_element,
                            'created_by': version.created_by,
                        }
                    )
                    
                    if created:
                        response_data['created']['elements'] += 1
                    else:
                        # Update existing element
                        if 'Description' in component_data:
                            element.description = component_data['Description'].replace('**', '')
                        if 'Dependencies' in component_data:
                            element.dependencies = dependencies_str
                        if 'Justification' in component_data:
                            element.justification = component_data['Justification']
                        if parent_element:
                            element.parent = parent_element
                        element.save()
                        response_data['updated']['elements'] += 1
                        
                except Exception as e:
                    response_data['errors'].append(f'Error processing component {component_data.get("Component Name", "unknown")}: {str(e)}')
        
        # Process Steady States
        if 'steadyStateJson' in data and 'steady_state_metrics' in data['steadyStateJson']:
            for steady_state_data in data['steadyStateJson']['steady_state_metrics']:
                try:
                    metric_name = steady_state_data.get('Metric Name')
                    if not metric_name:
                        response_data['errors'].append('Steady state missing Metric Name')
                        continue
                    
                    # Check if steady state exists by metric_name in this version
                    steady_state, created = SteadyState.objects.get_or_create(
                        version=version,
                        metric_name=metric_name,
                        defaults={
                            'category': steady_state_data.get('Category', ''),
                            'normal_behavior': steady_state_data.get('Normal Behavior', ''),
                            'deviation_indicators': steady_state_data.get('Deviation Indicators', ''),
                            'justification': steady_state_data.get('Justification', ''),
                            'created_by': version.created_by,
                        }
                    )
                    
                    if created:
                        response_data['created']['steady_states'] += 1
                    else:
                        # Update existing steady state
                        if 'Category' in steady_state_data:
                            steady_state.category = steady_state_data['Category']
                        if 'Normal Behavior' in steady_state_data:
                            steady_state.normal_behavior = steady_state_data['Normal Behavior']
                        if 'Deviation Indicators' in steady_state_data:
                            steady_state.deviation_indicators = steady_state_data['Deviation Indicators']
                        if 'Justification' in steady_state_data:
                            steady_state.justification = steady_state_data['Justification']
                        steady_state.save()
                        response_data['updated']['steady_states'] += 1
                        
                except Exception as e:
                    response_data['errors'].append(f'Error processing steady state {steady_state_data.get("Metric Name", "unknown")}: {str(e)}')
        
        # Process Hypotheses
        if 'hypothesisJson' in data and 'hypotheses' in data['hypothesisJson']:
            for hypothesis_data in data['hypothesisJson']['hypotheses']:
                try:
                    hypothesis_name = hypothesis_data.get('Hypothesis Name')
                    if not hypothesis_name:
                        response_data['errors'].append('Hypothesis missing Hypothesis Name')
                        continue
                    
                    # Check if hypothesis exists by name in this version
                    hypothesis, created = Hypothesis.objects.get_or_create(
                        version=version,
                        name=hypothesis_name,
                        defaults={
                            'description': hypothesis_data.get('Hypothesis Statement', '').replace('**', ''),
                            'justification': hypothesis_data.get('Justification', ''),
                            'created_by': version.created_by,
                        }
                    )
                    
                    if created:
                        response_data['created']['hypotheses'] += 1
                    else:
                        # Update existing hypothesis
                        if 'Hypothesis Statement' in hypothesis_data:
                            hypothesis.description = hypothesis_data['Hypothesis Statement'].replace('**', '')
                        if 'Justification' in hypothesis_data:
                            hypothesis.justification = hypothesis_data['Justification']
                        hypothesis.save()
                        response_data['updated']['hypotheses'] += 1
                    
                    # Handle component associations if provided (optional)
                    if 'Component Affected' in hypothesis_data and hypothesis_data['Component Affected']:
                        component_names = hypothesis_data['Component Affected']
                        elements = Element.objects.filter(version=version, name__in=component_names)
                        hypothesis.elements.set(elements)
                    
                    # Handle steady state associations if provided (optional)
                    if 'Affected Metrics' in hypothesis_data and hypothesis_data['Affected Metrics']:
                        metric_names = hypothesis_data['Affected Metrics']
                        steady_states = SteadyState.objects.filter(version=version, metric_name__in=metric_names)
                        hypothesis.steady_states.set(steady_states)
                        
                except Exception as e:
                    response_data['errors'].append(f'Error processing hypothesis {hypothesis_data.get("Hypothesis Name", "unknown")}: {str(e)}')
        
        # Process Experiments
        if 'experimentJson' in data and 'experiments' in data['experimentJson']:
            for experiment_data in data['experimentJson']['experiments']:
                try:
                    experiment_name = experiment_data.get('Experiment Name')
                    hypothesis_name = experiment_data.get('Hypothesis Being Tested')
                    
                    if not experiment_name:
                        response_data['errors'].append('Experiment missing Experiment Name')
                        continue
                    
                    if not hypothesis_name:
                        response_data['errors'].append(f'Experiment {experiment_name} missing Hypothesis Being Tested')
                        continue
                    
                    # Get the hypothesis
                    try:
                        hypothesis = Hypothesis.objects.get(version=version, name=hypothesis_name)
                    except Hypothesis.DoesNotExist:
                        response_data['errors'].append(f'Hypothesis "{hypothesis_name}" not found for experiment {experiment_name}')
                        continue
                    
                    # Check if experiment exists by name and hypothesis
                    experiment, created = Experiment.objects.get_or_create(
                        hypothesis=hypothesis,
                        name=experiment_name,
                        defaults={
                            'description':  experiment_data.get('Description', '').replace('**', ''),
                            'justification': experiment_data.get('Justification', ''),
                            'created_by': version.created_by,
                        }
                    )
                    
                    if created:
                        response_data['created']['experiments'] += 1
                    else:
                        # Update existing experiment
                        if 'Description' in experiment_data:
                            experiment.description = experiment_data['Description'].replace('**', '')
                        if 'Justification' in experiment_data:
                            experiment.justification = experiment_data['Justification']
                        experiment.save()
                        response_data['updated']['experiments'] += 1
                    
                    # Handle component associations if provided
                    if 'Components' in experiment_data and experiment_data['Components']:
                        component_names = experiment_data['Components']
                        elements = Element.objects.filter(version=version, name__in=component_names)
                        experiment.elements.set(elements)
                    
                    # Handle steady state associations if provided (new Metrics field)
                    if 'Metrics' in experiment_data and experiment_data['Metrics']:
                        metric_names = experiment_data['Metrics']
                        steady_states = SteadyState.objects.filter(version=version, metric_name__in=metric_names)
                        experiment.steady_states.set(steady_states)
                        
                except Exception as e:
                    response_data['errors'].append(f'Error processing experiment {experiment_data.get("Experiment Name", "unknown")}: {str(e)}')
        
        # Set success to False if there were errors
        if response_data['errors']:
            response_data['success'] = False
        
        return JsonResponse(response_data)
        
    except Version.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Version with UUID {version_uuid} not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'An error occurred: {str(e)}'}, status=500)

