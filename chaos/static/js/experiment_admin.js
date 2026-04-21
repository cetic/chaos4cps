(function ($) {
  "use strict";

  function waitForSelectAndInit() {
    console.log("Experiment Admin JS Loaded");
    const $hypothesisSelect = $("#id_hypothesis");
    const $elementsSelect = $("#id_elements");
    const $steadyStatesSelect = $("#id_steady_states");
    const $scriptsSelect = $("#id_scripts");

    console.log("Hypothesis Select:", $hypothesisSelect);
    console.log("Elements Select:", $elementsSelect);
    console.log("Steady States Select:", $steadyStatesSelect);
    console.log("Scripts Select:", $scriptsSelect);

    if (
      $hypothesisSelect.length === 0 ||
      $elementsSelect.length === 0 ||
      $steadyStatesSelect.length === 0
    ) {
      return false; // Try again later
    }
    console.log("Experiment Admin JS Loaded v2");

    function loadDataForHypothesis(hypothesisId) {
      // Save current selections
      const prevElementValues = $elementsSelect.val() || [];
      const prevSteadyStateValues = $steadyStatesSelect.val() || [];
      const prevScriptValues = $scriptsSelect.val() || [];

      console.log("Previous element values:", prevElementValues);
      console.log("Previous steady state values:", prevSteadyStateValues);
      console.log("Previous script values:", prevScriptValues);

      fetch(`/admin/chaos/experiment/load-data/?hypothesis=${hypothesisId}`)
        .then((response) => response.json())
        .then((data) => {
          // Populate elements
          $elementsSelect.empty();
          $elementsSelect.append('<option value="">Select elements</option>');
          data.elements.forEach((item) => {
            const isSelected = prevElementValues.includes(item.uuid);
            const option = new Option(item.name, item.uuid, false, isSelected);
            $elementsSelect.append(option);
          });

          // Populate steady states
          $steadyStatesSelect.empty();
          $steadyStatesSelect.append(
            '<option value="">Select steady states</option>'
          );
          data.steady_states.forEach((item) => {
            const isSelected = prevSteadyStateValues.includes(item.uuid);
            const option = new Option(item.name, item.uuid, false, isSelected);
            $steadyStatesSelect.append(option);
          });

          // Load scripts if available
          if (data.scripts) {
            $scriptsSelect.empty();
            $scriptsSelect.append('<option value="">Select scripts</option>');
            data.scripts.forEach((item) => {
              const isSelected = prevScriptValues.includes(item.uuid);
              const option = new Option(
                item.name,
                item.uuid,
                false,
                isSelected
              );
              $scriptsSelect.append(option);
            });
          }

          $elementsSelect.trigger("change");
          $steadyStatesSelect.trigger("change");
          if ($scriptsSelect.length) {
            $scriptsSelect.trigger("change");
          }
        })
        .catch((error) => {
          console.error("Error loading data for hypothesis:", error);
        });
    }

    // Initialize with current hypothesis if available
    let initialHypothesisId = $hypothesisSelect.val();
    if (initialHypothesisId) {
      loadDataForHypothesis(initialHypothesisId);
    } else {
      // Clear fields if no hypothesis selected
      $elementsSelect
        .empty()
        .append('<option value="">Select elements</option>');
      $steadyStatesSelect
        .empty()
        .append('<option value="">Select steady states</option>');
      if ($scriptsSelect.length) {
        $scriptsSelect
          .empty()
          .append('<option value="">Select scripts</option>');
      }
    }

    // Handle hypothesis change
    $hypothesisSelect.on("change", function () {
      const hypothesisId = $(this).val();
      if (initialHypothesisId !== hypothesisId) {
        initialHypothesisId = hypothesisId;
        if (hypothesisId) {
          loadDataForHypothesis(hypothesisId);
        } else {
          // Clear fields if no hypothesis selected
          $elementsSelect
            .empty()
            .append('<option value="">Select elements</option>');
          $steadyStatesSelect
            .empty()
            .append('<option value="">Select steady states</option>');
          if ($scriptsSelect.length) {
            $scriptsSelect
              .empty()
              .append('<option value="">Select scripts</option>');
          }
        }
      }
    });

    // Enhanced form validation
    function validateForm() {
      const hypothesis = $hypothesisSelect.val();
      const elements = $elementsSelect.val();
      const steadyStates = $steadyStatesSelect.val();

      let isValid = true;
      let errorMessages = [];

      if (!hypothesis) {
        errorMessages.push("Please select a hypothesis");
        isValid = false;
      }

      if (!elements || elements.length === 0) {
        errorMessages.push("Please select at least one element");
        isValid = false;
      }

      if (!steadyStates || steadyStates.length === 0) {
        errorMessages.push("Please select at least one steady state");
        isValid = false;
      }

      // Display validation errors if any
      if (!isValid) {
        const errorDiv = $(
          '<div class="error-message" style="color: red; margin: 10px 0; padding: 10px; background: #ffe6e6; border: 1px solid #ff9999; border-radius: 4px;"></div>'
        );
        errorDiv.html(
          "<strong>Please correct the following errors:</strong><ul><li>" +
            errorMessages.join("</li><li>") +
            "</li></ul>"
        );

        // Remove existing error messages
        $(".error-message").remove();

        // Insert error message before the form
        $("form").prepend(errorDiv);
      } else {
        // Remove error messages if form is valid
        $(".error-message").remove();
      }

      return isValid;
    }

    // Add validation to form submission
    $("form").on("submit", function (e) {
      if (!validateForm()) {
        e.preventDefault();
        return false;
      }
    });

    // Add helpful tooltips and descriptions
    function addHelpfulUI() {
      // Add help text for hypothesis selection
      if (
        $hypothesisSelect.length &&
        !$hypothesisSelect.next(".help-text").length
      ) {
        $hypothesisSelect.after(
          '<div class="help-text" style="font-size: 12px; color: #666; margin-top: 5px;">Select a hypothesis to automatically populate available elements and steady states</div>'
        );
      }

      // Add help text for elements selection
      if (
        $elementsSelect.length &&
        !$elementsSelect.next(".help-text").length
      ) {
        $elementsSelect.after(
          '<div class="help-text" style="font-size: 12px; color: #666; margin-top: 5px;">Select the elements that will be affected by this experiment</div>'
        );
      }

      // Add help text for steady states selection
      if (
        $steadyStatesSelect.length &&
        !$steadyStatesSelect.next(".help-text").length
      ) {
        $steadyStatesSelect.after(
          '<div class="help-text" style="font-size: 12px; color: #666; margin-top: 5px;">Select the steady states that will be monitored during this experiment</div>'
        );
      }
    }

    // Initialize helpful UI
    addHelpfulUI();

    return true; // Initialization successful
  }

  // Initialize when DOM is ready
  $(document).ready(function () {
    setTimeout(waitForSelectAndInit, 100);
  });

  // Also initialize when the page is loaded via AJAX
  $(document).on("formset:added", function (event, $row, formsetName) {
    setTimeout(waitForSelectAndInit, 100);
  });
})(window.django && django.jQuery ? django.jQuery : window.jQuery || window.$);
