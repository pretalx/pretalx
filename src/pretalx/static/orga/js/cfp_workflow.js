var api = {
  submit(data) {
    var fullHeaders = {}
    fullHeaders["Content-Type"] = "application/json"
    fullHeaders["X-CSRFToken"] = getCookie("pretalx_csrftoken")

    let options = {
      method: "POST",
      headers: fullHeaders,
      credentials: "include",
      body: data && JSON.stringify(data),
    }
    return window
      .fetch(window.location, options)
      .then(response => {
        if (response.status === 204) {
          return Promise.resolve()
        }
        return response.json().then(json => {
          if (!response.ok) {
            return Promise.reject({ response, json })
          }
          return Promise.resolve(json)
        })
      })
      .catch(error => {
        return Promise.reject(error)
      })
  },
}

var dragController = {
  draggedField: null,
  event: null,
  stepWindow: null,
  dragPosX: null,
  dragPosY: null,
  dragSource: null,

  startDragging(field, dragSource, dragPosX, dragPosY) {
    this.draggedField = JSON.parse(JSON.stringify(field))
    this.dragPosX = dragPosX
    this.dragSource = dragSource
    this.dragPosY = dragPosY
    this.dragSource.classList.add("drag-source")
  },
  stopDragging() {
    if (this.stepWindow) {
      this.stepWindow.classList.remove("hover-active")
      this.stepWindow.classList.remove("drag-source")
      this.draggedField = null
      this.event = null
    }
  },
}

let currentLanguage = "en"

Vue.component("field", {
  template: `
    <div :class="['form-group', 'row', field.field_source, {dragged: isDragged}]" v-bind:style="style" @mousedown="onMouseDown">
      <label class="col-md-3 col-form-label">
        {{ field.title }}
        <span v-if="!field.required & !field.hard_required" class="optional" @click="field.required=true"><br>Optional</span>
        <span v-else-if="!field.hard_required" class="optional" @click="field.required=false"><br><strong>Required</strong></span>
        <span v-else class="optional"><br><strong>Required</strong></span>
      </label>
      <div class="col-md-9">
        <input class="form-control" type="text" :placeholder="field.title" readonly v-if="field.widget === 'TextInput'">
        <select class="form-control" type="text" :placeholder="field.title" readonly v-else-if="field.widget === 'Select'"></select>
        <textarea class="form-control" type="text" :placeholder="field.title" readonly v-else-if="field.widget === 'Textarea'"></textarea>

        <small class="form-text text-muted" v-if="help_text">{{ help_text[currentLanguage] }}</small>
      </div>
    </div>
  `, // TODO: file upload, checkboxes, help_text to html
  data() {
    return {}
  },
  props: {
    field: Object,
    isDragged: { type: Boolean, default: false },
    isActive: { type: Boolean, default: false },
  },
  computed: {
    style () {
      if (this.isDragged) {
        return {position: "absolute"}
      }
      return ""
    },
    help_text () {
      return this.field.help_text || this.field.defaultHelpText
    }
  },
  methods: {
    onMouseDown(event) {
      if (event.buttons === 1) {
        var fieldRect = this.$el.getBoundingClientRect()
        dragController.startDragging(
          this.field,
          this.$el,
          event.clientX - fieldRect.left,
          event.clientY - fieldRect.top
        )
      }
    },
  },
})

Vue.component("step", { // TODO: introduce a modal, let steps be dragged
  template: `
    <div class="step">
      <div :class="['step-header', 'header', eventConfiguration.header_pattern]" :style="headerStyle">
        <img :src="eventConfiguration.header_image" v-if="eventConfiguration.header_image">
      </div>
      <div class="step-main-container">
        <div class="submission-steps stages">
          <span :class="['step', 'step-' + stp.phase]" v-for="stp in headerSteps">
              <div class="step-icon">
                  <span :class="['fa', 'fa-' + stp.icon]"></span>
              </div>
              <div class="step-label">
                  {{ stp.label }}
              </div>
          </span>
        </div>
        <h2 @click="editingTitle=true" class="editable">
          <span v-if="!editingTitle">{{ step.title[currentLanguage] }}</span>
          <span v-else><input type="text" v-model="step.title"/></span>
        </h2>
        {{ step.text[currentLanguage] }}
        <form v-if="step.identifier != 'auth'">
          <field v-for="field in step.fields" :field="field" :key="field.title"></field>
        </form>
        <form v-else id="auth-form">
          <div class="auth-form-block">
            <h4 class="text-center">I already have an account</h4>
            <div class="form-group"><input type="text" class="form-control" placeholder="Email address" readonly></div>
            <div class="form-group"><input type="password" class="form-control" placeholder="Password" readonly></div>
            <button type="submit" class="btn btn-lg btn-success btn-block" disabled>Log in</button>
          </div>
          <div class="auth-form-block">
            <h4 class="text-center">I need a new account</h4>
            <div class="form-group"><input type="text" class="form-control" placeholder="Name" readonly></div>
            <div class="form-group"><input type="text" class="form-control" placeholder="Email address" readonly></div>
            <div class="form-group"><input type="password" class="form-control" placeholder="Password" readonly></div>
            <div class="form-group"><input type="password" class="form-control" placeholder="Password (again)" readonly></div>
            <button type="submit" class="btn btn-lg btn-info btn-block" disabled>Register</button>
            <div class="overlay">
              This form cannot be modified – a page to login or register needs to be in place, but you can change the page title and description.
            </div>
        </form>
      </div>
    </div>
  `,
  data() {
    return {
      editingTitle: false,
      editingText: false,
    }
  },
  props: {
    eventConfiguration: Object,
    step: Object,
    steps: Array,
  },
  computed: {
    headerStyle () {
      // logo_image, header_image, header_pattern
      return {
        "background-color": this.eventConfiguration.primary_color || "#1a4c3b",
      }
    },
    stepPosition () {
      return this.steps.findIndex((element) => { return element.fields === this.fields })
    },
    headerSteps () {
      let result = this.steps.map((element, index) => {
        let state = null;
        if (index < this.stepPosition) { state = "done" }
        else if (index === this.stepPosition) { state = "current" }
        else { state = "todo" }
        return {
          "icon": state === "done" ? "check" : element.icon,
          "label": element.header_label,
          "phase": state,
        }
      })
      result.push({
        "icon": "done",
        "label": "Done!",
        "phase": "todo"
      })
    }
  },
})

var app = new Vue({
  el: "#workflow",
  template: `
    <div @mousemove="onMouseMove" @mouseup="onMouseUp">
      <div id="workflow">
        <field ref="draggedField" v-if="dragController.draggedField && dragController.event" :field="dragController.draggedField" :key="dragController.draggedField" :is-dragged="true"></field>
        <div id="loading" v-if="loading">
            <i class="fa fa-spinner fa-pulse fa-4x fa-fw text-primary mb-4 mt-4"></i>
            <h3 class="mt-2 mb-4">Loading talks, please wait.</h3>
        </div>
        <div id="steps" v-else>
          <step v-for="step in stepsConfiguration.steps" :step="step" :eventConfiguration="eventConfiguration" :key="step.identifier" :steps="stepsConfiguration.steps">
          </step>
        </div>
      </div>
      <div id="unassigned-group">
        <div class="step-header" ref="stepHeader">Unassigned Fields</div>
        <div id='unassigned-fields'>
          <div class="input-group">
            <div class="input-group-prepend input-group-text"><i class="fa fa-search"></i></div>
            <input type="text" class="form-control" placeholder="Search..." v-model="search">
          </div>
          <div id="unassigned-container" ref="unassigned">
              <field v-for="field in filteredFields" :field="field" :key="field.id"></field>
          </div>
        </div>
      </div>
    </div>
  `,
  data() {
    return {
      steps: null,
      fieldLookup: null,
      unassignedFields: null,
      search: "",
      dragController: dragController,
      loading: true,
      eventSlug: "",
      eventConfiguration: null,
      stepsConfiguration: null,
      originalConfiguration: null,
      locales: null
    }
  },
  created() {
    this.eventConfiguration = JSON.parse(document.getElementById('eventConfiguration').textContent);
    this.locales = this.eventConfiguration.locales;
    if (!this.locales.includes("en")) currentLanguage = this.locales[0];
    let allFields = JSON.parse(document.getElementById('allFields').textContent);
    this.fieldLookup = allFields.reduce((accumulator, currentValue) => {
      currentValue.key = currentValue.field_type + '_' + currentValue.field_source
      accumulator[currentValue.key] = currentValue
      return accumulator
    }, {})
    this.unassignedFields = JSON.parse(JSON.stringify(this.fieldLookup))
    let currentConfiguration = JSON.parse(document.getElementById('currentConfiguration').textContent);
    this.eventSlug = currentConfiguration.event
    this.stepsConfiguration = currentConfiguration
    this.stepsConfiguration.steps.forEach((step) => {
      if (!step.fields) {
        return
      }
      step.fields.forEach((field) => {
        const defaultField = this.fieldLookup[field.field_type + '_' + field.field_source]
        field.key = defaultField.key
        field.hardRequired = defaultField.hardRequired
        field.defaultHelpText = defaultField.help_text
        field.title = defaultField.title
        field.widget = defaultField.widget
        delete this.unassignedFields[field.key]
      })
    })
    this.loading = false
  },
  computed: {
    filteredFields() {
      if (!this.unassignedFields) return []
      return Object.values(this.unassignedFields).filter(field => {
        return field.title.toLowerCase().indexOf(this.search.toLowerCase()) > -1
      })
    },
    configurationChanged() {
      return false // TODO: compare this.originalConfiguration and this.stepsConfiguration
    },
  },
  methods: {
    onMouseMove(event) {
      if (dragController.draggedField) {
        dragController.event = event
        var newStep = document.elementFromPoint(
          event.clientX,
          event.clientY
        )

        while (
          !newRoomColumn.className.match(/room-container/) &&
          newRoomColumn.id !== "unassigned-container" &&
          newRoomColumn.parentElement
        ) {
          newRoomColumn = newRoomColumn.parentElement
        }

        if (newRoomColumn.dataset.id) {
          if (newRoomColumn && newRoomColumn !== dragController.roomColumn) {
            if (dragController.roomColumn)
              dragController.roomColumn.classList.remove("hover-active")
          }
          dragController.roomColumn = newRoomColumn
          dragController.draggedTalk.room = newRoomColumn.dataset.id
          dragController.roomColumn.classList.add("hover-active")
          if (dragController.roomColumn && app.$refs.draggedTalk) {
            var colRect = dragController.roomColumn.getBoundingClientRect()
            var dragRect = app.$refs.draggedTalk.$el.getBoundingClientRect()
            var position = dragRect.top - colRect.top
            position -= position % 5
            dragController.draggedTalk.start = moment(this.start)
              .add(position, "minutes")
              .format()
          }
        } else if (newRoomColumn.id === "unassigned-container") {
          if (newRoomColumn && newRoomColumn !== dragController.roomColumn) {
            if (dragController.roomColumn)
              dragController.roomColumn.classList.remove("hover-active")
          }
          dragController.roomColumn = newRoomColumn
          dragController.draggedTalk.room = null
          dragController.draggedTalk.start = null
          dragController.roomColumn.classList.add("hover-active")
        }

        if (event.clientY < 160) {
          if (event.clientY < 110) {
            window.scrollBy({
              top: -100,
              behavior: "smooth",
            })
          } else {
            window.scrollBy({
              top: -50,
              behavior: "smooth",
            })
          }
        } else if (event.clientY > window.innerHeight - 100) {
          if (event.clientY > window.innerHeight - 40) {
            window.scrollBy({
              top: 100,
              behavior: "smooth",
            })
          } else {
            window.scrollBy({
              top: 50,
              behavior: "smooth",
            })
          }
        }
      }
    },
    onMouseUp(event) {
      if (dragController.draggedTalk) {
        if (dragController.event) {
          api.saveTalk(dragController.draggedTalk).then(response => {
            this.talks.forEach((talk, index) => {
              if (talk.id == response.id) {
                Object.assign(this.talks[index], response)
              }
            })
          })
        } else {
          window.open(dragController.draggedTalk.url)
          dragController.stopDragging()
        }
      }
      dragController.stopDragging()
    },
  },
})
