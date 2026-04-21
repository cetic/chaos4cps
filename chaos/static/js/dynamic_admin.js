(function ($) {
  "use strict";

  // Configuration for different admin forms
  const formConfigs = {
    element: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      parentField: "#id_parent",
      dataType: "suts",
    },
    version: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      dataType: "suts",
    },
    steadystate: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      scriptField: "#id_script",
      dataType: "suts",
    },
    hypothesis: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      elementsField: "#id_elements",
      steadyStatesField: "#id_steady_states",
      dataType: "suts",
    },
    experiment: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      hypothesisField: "#id_hypothesis",
      elementsField: "#id_elements",
      steadyStatesField: "#id_steady_states",
      scriptForParametersField: "#id_script_for_parameters",
      dataType: "suts",
    },
    execution: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      hypothesisField: "#id_hypothesis",
      experimentField: "#id_experiment",
      scriptField: "#id_script",
      dataType: "suts",
    },
    recovery: {
      customerField: "#id_customer",
      sutField: "#id_sut",
      versionField: "#id_version",
      hypothesisField: "#id_hypothesis",
      experimentField: "#id_experiment",
      executionField: "#id_execution",
      scriptField: "#id_script",
      dataType: "suts",
    },
  };

  // Determine which form we're on
  function getFormType() {
    const path = window.location.pathname;
    if (path.includes("/element/")) return "element";
    if (path.includes("/version/")) return "version";
    if (path.includes("/steadystate/")) return "steadystate";
    if (path.includes("/hypothesis/")) return "hypothesis";
    if (path.includes("/experiment/")) return "experiment";
    if (path.includes("/execution/")) return "execution";
    if (path.includes("/recovery/")) return "recovery";
    return null;
  }

  // Get the current form configuration
  function getFormConfig() {
    const formType = getFormType();
    return formConfigs[formType] || null;
  }

  // Clear and disable a select field
  function clearSelect(fieldSelector, placeholder = "Select an option") {
    const $field = $(fieldSelector);
    if ($field.length) {
      $field.empty().append(`<option value="">${placeholder}</option>`);
      $field.prop("disabled", true);
    }
  }

  // Populate a select field with options
  function populateSelect(
    fieldSelector,
    data,
    valueKey = "uuid",
    labelKey = "name",
    placeholder = "Select an option",
    preserveValue = true
  ) {
    const $field = $(fieldSelector);
    if ($field.length) {
      // Store current value to preserve it if it exists in the new data
      const currentValue = $field.val();

      $field.empty().append(`<option value="">${placeholder}</option>`);

      data.forEach((item) => {
        const option = new Option(item[labelKey], item[valueKey], false, false);
        $field.append(option);
      });

      // Restore the previous value if it exists in the new options and preserveValue is true
      if (
        preserveValue &&
        currentValue &&
        $field.find(`option[value="${currentValue}"]`).length > 0
      ) {
        $field.val(currentValue);
      }

      $field.prop("disabled", false);
      // Don't trigger change event if we're preserving a value to avoid infinite loops
      if (
        !preserveValue ||
        !currentValue ||
        $field.find(`option[value="${currentValue}"]`).length === 0
      ) {
        $field.trigger("change");
      }
    }
  }

  // Load data from server
  function loadData(dataType, params) {
    const url = new URL(
      window.location.origin +
        "/admin/chaos/" +
        getFormType() +
        "/dynamic-data/"
    );
    url.search = new URLSearchParams({
      type: dataType,
      ...params,
    }).toString();

    return fetch(url)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
      })
      .catch((error) => {
        console.error("Error loading data:", error);
        return {};
      });
  }

  // Handle customer selection
  function handleCustomerChange(config) {
    const customerId = $(config.customerField).val();

    if (!customerId) {
      // Clear dependent fields
      clearSelect(config.sutField, "Select a SUT");
      clearSelect(config.versionField, "Select a version");
      if (config.parentField)
        clearSelect(config.parentField, "Select a parent element");
      if (config.hypothesisField)
        clearSelect(config.hypothesisField, "Select a hypothesis");
      if (config.elementsField)
        clearSelect(config.elementsField, "Select elements");
      if (config.steadyStatesField)
        clearSelect(config.steadyStatesField, "Select steady states");
      return;
    }

    // Load SUTs for the selected customer
    loadData("suts", { customer: customerId }).then((data) => {
      populateSelect(
        config.sutField,
        data.suts || [],
        "uuid",
        "name",
        "Select a SUT"
      );

      // Clear dependent fields
      clearSelect(config.versionField, "Select a version");
      if (config.parentField)
        clearSelect(config.parentField, "Select a parent element");
      if (config.hypothesisField)
        clearSelect(config.hypothesisField, "Select a hypothesis");
      if (config.elementsField)
        clearSelect(config.elementsField, "Select elements");
      if (config.steadyStatesField)
        clearSelect(config.steadyStatesField, "Select steady states");
    });
  }

  // Handle SUT selection
  function handleSutChange(config) {
    const sutId = $(config.sutField).val();

    if (!sutId) {
      // Clear dependent fields
      clearSelect(config.versionField, "Select a version");
      if (config.parentField)
        clearSelect(config.parentField, "Select a parent element");
      if (config.hypothesisField)
        clearSelect(config.hypothesisField, "Select a hypothesis");
      if (config.elementsField)
        clearSelect(config.elementsField, "Select elements");
      if (config.steadyStatesField)
        clearSelect(config.steadyStatesField, "Select steady states");
      return;
    }

    // Load versions for the selected SUT
    loadData("versions", { sut: sutId }).then((data) => {
      populateSelect(
        config.versionField,
        data.versions || [],
        "uuid",
        "name",
        "Select a version"
      );

      // Clear dependent fields
      if (config.parentField)
        clearSelect(config.parentField, "Select a parent element");
      if (config.hypothesisField)
        clearSelect(config.hypothesisField, "Select a hypothesis");
      if (config.elementsField)
        clearSelect(config.elementsField, "Select elements");
      if (config.steadyStatesField)
        clearSelect(config.steadyStatesField, "Select steady states");
    });
  }

  // Load dependent fields for a version (elements, steady states, hypotheses, parents)
  function loadVersionDependents(config, versionId, preserveValues = false) {
    const promises = [];

    // Load elements if field exists
    if (config.elementsField) {
      promises.push(
        loadData("elements", { version: versionId }).then((data) => {
          populateSelect(
            config.elementsField,
            data.elements || [],
            "uuid",
            "name",
            "Select elements",
            preserveValues
          );
        })
      );
    }

    // Load steady states if field exists
    if (config.steadyStatesField) {
      promises.push(
        loadData("steady_states", { version: versionId }).then((data) => {
          populateSelect(
            config.steadyStatesField,
            data.steady_states || [],
            "uuid",
            "metric_name",
            "Select steady states",
            preserveValues
          );
        })
      );
    }

    // Load hypotheses if field exists
    if (config.hypothesisField) {
      promises.push(
        loadData("hypotheses", { version: versionId }).then((data) => {
          populateSelect(
            config.hypothesisField,
            data.hypotheses || [],
            "uuid",
            "name",
            "Select a hypothesis",
            preserveValues
          );
        })
      );
    }

    // Load parent elements if field exists (excluding current element for edit mode)
    if (config.parentField) {
      // Get current element ID for exclusion (only for element forms)
      const elementId = window.location.pathname.match(
        /\/(\w+-\w+-\w+-\w+-\w+)\/change\//
      );
      let params = { version: versionId };
      if (elementId && elementId[1] && elementId[1].trim() !== "") {
        params.element_id = elementId[1];
      }

      promises.push(
        loadData("parents", params).then((data) => {
          populateSelect(
            config.parentField,
            data.parents || [],
            "uuid",
            "name",
            "Select a parent element",
            preserveValues
          );
        })
      );
    }

    return Promise.all(promises);
  }

  // Handle hypothesis selection
  function handleHypothesisChange(config) {
    const hypothesisId = $(config.hypothesisField).val();

    if (!hypothesisId) {
      // Clear dependent fields
      if (config.experimentField)
        clearSelect(config.experimentField, "Select an experiment");
      if (config.executionField)
        clearSelect(config.executionField, "Select an execution");
      return;
    }

    // Load experiments for the selected hypothesis
    if (config.experimentField) {
      loadData("experiments", { hypothesis: hypothesisId }).then((data) => {
        populateSelect(
          config.experimentField,
          data.experiments || [],
          "uuid",
          "name",
          "Select an experiment"
        );

        // Clear dependent fields
        if (config.executionField)
          clearSelect(config.executionField, "Select an execution");
      });
    }
  }

  // Handle experiment selection
  function handleExperimentChange(config) {
    const experimentId = $(config.experimentField).val();

    if (!experimentId) {
      // Clear dependent fields
      if (config.executionField)
        clearSelect(config.executionField, "Select an execution");
      return;
    }

    // Load executions for the selected experiment
    if (config.executionField) {
      loadData("executions", { experiment: experimentId }).then((data) => {
        populateSelect(
          config.executionField,
          data.executions || [],
          "uuid",
          "status",
          "Select an execution"
        );
      });
    }
  }

  // Handle script selection (load parameters for the selected script)
  function handleScriptChange(config) {
    const scriptField = config.scriptField || config.scriptForParametersField;
    if (!scriptField) return;

    const scriptId = $(scriptField).val();

    if (!scriptId) {
      // Hide parameter section when no script is selected
      hideParameterSection();
      return;
    }

    // Load parameters for the selected script
    loadData("script_parameters", { script: scriptId }).then((data) => {
      displayScriptParameters(data.parameters || [], scriptId);
    });
  }

  // Display script parameters in a dedicated section
  function displayScriptParameters(parameters, scriptId) {
    console.log("Displaying parameters for script:", scriptId, parameters);

    // Find or create a parameters container
    let parametersContainer = document.getElementById(
      "script-parameters-container"
    );
    if (!parametersContainer) {
      parametersContainer = document.createElement("div");
      parametersContainer.id = "script-parameters-container";
      parametersContainer.innerHTML = "<h3>Script Parameters</h3>";

      // Insert after the script field
      const scriptField = document.querySelector(
        "#id_script, #id_script_for_parameters"
      );
      if (scriptField) {
        scriptField
          .closest(".form-row")
          .parentNode.insertBefore(
            parametersContainer,
            scriptField.closest(".form-row").nextSibling
          );
      }
    }

    // Clear existing content except title
    parametersContainer.innerHTML = "<h3>Script Parameters</h3>";

    if (parameters.length === 0) {
      parametersContainer.innerHTML +=
        "<p>No parameters defined for this script.</p>";
      return;
    }

    // Create parameter fields
    parameters.forEach((param) => {
      const paramDiv = document.createElement("div");
      paramDiv.className = "form-row";

      let inputField = "";
      switch (param.parameter_type) {
        case "boolean":
          inputField = `<input type="checkbox" id="param_${
            param.uuid
          }" name="param_${param.uuid}" ${
            param.default_value === "true" ? "checked" : ""
          }>`;
          break;
        case "integer":
        case "float":
          inputField = `<input type="number" id="param_${
            param.uuid
          }" name="param_${param.uuid}" value="${param.default_value || ""}" ${
            param.parameter_type === "float" ? 'step="any"' : ""
          }>`;
          break;
        case "file":
          inputField = `<input type="file" id="param_${param.uuid}" name="param_${param.uuid}">`;
          break;
        default:
          inputField = `<input type="text" id="param_${
            param.uuid
          }" name="param_${param.uuid}" value="${param.default_value || ""}">`;
      }

      paramDiv.innerHTML = `
        <label for="param_${param.uuid}">
          ${param.name} ${param.required ? "*" : ""}
        </label>
        ${inputField}
        ${param.description ? `<p class="help">${param.description}</p>` : ""}
      `;

      parametersContainer.appendChild(paramDiv);
    });
  }

  // Hide parameter section
  function hideParameterSection() {
    const parametersContainer = document.getElementById(
      "script-parameters-container"
    );
    if (parametersContainer) {
      parametersContainer.style.display = "none";
    }
  }

  // Handle version selection
  function handleVersionChange(config) {
    const versionId = $(config.versionField).val();

    if (!versionId) {
      // Clear dependent fields
      if (config.parentField)
        clearSelect(config.parentField, "Select a parent element");
      if (config.hypothesisField)
        clearSelect(config.hypothesisField, "Select a hypothesis");
      if (config.elementsField)
        clearSelect(config.elementsField, "Select elements");
      if (config.steadyStatesField)
        clearSelect(config.steadyStatesField, "Select steady states");
      return;
    }

    // Load dependent fields (don't preserve values for manual changes)
    loadVersionDependents(config, versionId, false).catch((error) => {
      console.error("Error loading version-dependent data:", error);
    });
  }

  // Initialize dynamic form behavior
  function initDynamicForm() {
    const config = getFormConfig();
    if (!config) return;

    console.log("Initializing dynamic form for:", getFormType());

    // Set up event handlers
    $(config.customerField).on("change", function () {
      handleCustomerChange(config);
    });

    $(config.sutField).on("change", function () {
      handleSutChange(config);
    });

    // Only set up version handler if version field exists
    if (config.versionField) {
      $(config.versionField).on("change", function () {
        handleVersionChange(config);
      });
    }

    // Set up hypothesis handler if hypothesis field exists
    if (config.hypothesisField) {
      $(config.hypothesisField).on("change", function () {
        handleHypothesisChange(config);
      });
    }

    // Set up experiment handler if experiment field exists
    if (config.experimentField) {
      $(config.experimentField).on("change", function () {
        handleExperimentChange(config);
      });
    }

    // Set up script handler if script field exists
    if (config.scriptField) {
      $(config.scriptField).on("change", function () {
        handleScriptChange(config);
      });
    }

    // Set up script_for_parameters handler if script_for_parameters field exists
    if (config.scriptForParametersField) {
      $(config.scriptForParametersField).on("change", function () {
        handleScriptChange(config);
      });
    }

    // Initialize form state based on existing values
    const customerId = $(config.customerField).val();
    const sutId = $(config.sutField).val();
    const versionId = config.versionField ? $(config.versionField).val() : null;
    const hypothesisId = config.hypothesisField
      ? $(config.hypothesisField).val()
      : null;
    const experimentId = config.experimentField
      ? $(config.experimentField).val()
      : null;
    const executionId = config.executionField
      ? $(config.executionField).val()
      : null;
    const scriptId = config.scriptField ? $(config.scriptField).val() : null;
    const scriptForParametersId = config.scriptForParametersField
      ? $(config.scriptForParametersField).val()
      : null;

    console.log("Initial values detected:", {
      customerId,
      sutId,
      versionId,
      hypothesisId,
      experimentId,
      executionId,
      scriptId,
      scriptForParametersId,
    });

    // If we have initial values, we're in edit mode - load options but preserve selections
    if (customerId && sutId) {
      console.log("Edit mode detected - preserving initial values");
      // Load SUTs for customer but keep current selection
      loadData("suts", { customer: customerId }).then((data) => {
        populateSelect(
          config.sutField,
          data.suts || [],
          "uuid",
          "name",
          "Select a SUT",
          true // preserve current value
        );
      });
    } else if (customerId) {
      // Only customer selected, load SUTs and clear others
      handleCustomerChange(config);
    }

    if (sutId && versionId && config.versionField) {
      console.log("Loading versions for edit mode");
      // Load versions for SUT but keep current selection
      loadData("versions", { sut: sutId }).then((data) => {
        populateSelect(
          config.versionField,
          data.versions || [],
          "uuid",
          "name",
          "Select a version",
          true // preserve current value
        );
      });
    } else if (sutId && config.versionField) {
      // Only SUT selected, load versions and clear others
      handleSutChange(config);
    }

    if (versionId && config.versionField) {
      // Load dependent fields for version but preserve selections
      loadVersionDependents(config, versionId, true);
    }

    // Initialize hypothesis-dependent fields in edit mode
    if (
      hypothesisId &&
      experimentId &&
      config.hypothesisField &&
      config.experimentField
    ) {
      console.log("Loading experiments for edit mode");
      // Load experiments for hypothesis but keep current selection
      loadData("experiments", { hypothesis: hypothesisId }).then((data) => {
        populateSelect(
          config.experimentField,
          data.experiments || [],
          "uuid",
          "name",
          "Select an experiment",
          true // preserve current value
        );
      });
    } else if (hypothesisId && config.hypothesisField) {
      // Only hypothesis selected, load experiments and clear others
      handleHypothesisChange(config);
    }

    // Initialize experiment-dependent fields in edit mode
    if (
      experimentId &&
      executionId &&
      config.experimentField &&
      config.executionField
    ) {
      console.log("Loading executions for edit mode");
      // Load executions for experiment but keep current selection
      loadData("executions", { experiment: experimentId }).then((data) => {
        populateSelect(
          config.executionField,
          data.executions || [],
          "uuid",
          "status",
          "Select an execution",
          true // preserve current value
        );
      });
    } else if (experimentId && config.experimentField) {
      // Only experiment selected, load executions and clear others
      handleExperimentChange(config);
    }

    // Initialize script parameters in edit mode
    if (scriptId && config.scriptField) {
      console.log("Loading script parameters for edit mode");
      handleScriptChange(config);
    }

    if (scriptForParametersId && config.scriptForParametersField) {
      console.log("Loading script_for_parameters parameters for edit mode");
      handleScriptChange(config);
    }

    // If no initial values, disable dependent fields
    if (!customerId) {
      $(config.sutField).prop("disabled", true);
    }
    if (!sutId && config.versionField) {
      $(config.versionField).prop("disabled", true);
    }
    if (!versionId && config.versionField) {
      if (config.parentField) $(config.parentField).prop("disabled", true);
      if (config.hypothesisField)
        $(config.hypothesisField).prop("disabled", true);
      if (config.elementsField) $(config.elementsField).prop("disabled", true);
      if (config.steadyStatesField)
        $(config.steadyStatesField).prop("disabled", true);
    }
    if (!hypothesisId && config.hypothesisField) {
      if (config.experimentField)
        $(config.experimentField).prop("disabled", true);
      if (config.executionField)
        $(config.executionField).prop("disabled", true);
    }
    if (!experimentId && config.experimentField) {
      if (config.executionField)
        $(config.executionField).prop("disabled", true);
    }
  }

  // Wait for DOM to be ready and initialize
  $(document).ready(function () {
    // Small delay to ensure all form elements are loaded
    setTimeout(initDynamicForm, 100);
  });

  // Also initialize when the page is loaded via AJAX (for admin inline forms)
  $(document).on("formset:added", function (event, $row, formsetName) {
    setTimeout(initDynamicForm, 100);
  });
})(window.django && django.jQuery ? django.jQuery : window.jQuery || window.$);
