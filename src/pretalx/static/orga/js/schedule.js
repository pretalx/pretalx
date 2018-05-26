var api = {
  cache: {},
  http (verb, url, body) {
    var fullHeaders = {}
    fullHeaders['Content-Type'] = 'application/json'
    fullHeaders['X-CSRFToken'] = getCookie('pretalx_csrftoken')
    console.log(fullHeaders)

    let options = {
      method: verb || 'GET',
      headers: fullHeaders,
      credentials: 'include',
      body: body && JSON.stringify(body)
    }
    return window.fetch(url, options).then((response) => {
      if (response.status === 204) {
        return Promise.resolve()
      }
      return response.json().then((json) => {
        if (!response.ok) {
          return Promise.reject({response, json})
        }
        return Promise.resolve(json)
      })
    }).catch((error) => {
      return Promise.reject(error)
    })
  },
  fetchTalks () {
    var url = [window.location.protocol, '//', window.location.host, window.location.pathname, 'api/talks/', window.location.search].join('')
    return api.http('GET', url, null)
  },
  fetchRooms () {
    var url = [window.location.protocol, '//', window.location.host, window.location.pathname, 'api/rooms/', window.location.search].join('')
    return api.http('GET', url, null)
  },
  fetchAvailabilities (talkid, roomid, check_cache=true) {
    var url = [window.location.protocol, '//', window.location.host, window.location.pathname, `api/availabilities/${talkid}/${roomid}/`, window.location.search].join('')

    if (check_cache && api.cache[url]) {
      return api.cache[url];
    } else {
      api.cache[url] = api.http('GET', url, null);
    }

    return api.cache[url];
  },
  saveTalk(talk) {
    var url = [window.location.protocol, '//', window.location.host, window.location.pathname, `api/talks/${talk.id}/`, window.location.search].join('')
    return api.http('PATCH', url, {
      room: talk.room,
      start: talk.start,
    })
  }
}

var dragController = {
  draggedTalk: null,
  event: null,
  roomColumn: null,
  dragPosX: null,
  dragPosY: null,
  dragSource: null,

  startDragging (talk, dragSource, dragPosX, dragPosY) {
    this.draggedTalk = JSON.parse(JSON.stringify(talk))
    this.dragPosX = dragPosX
    this.dragSource = dragSource
    this.dragPosY = dragPosY
    this.dragSource.classList.add('drag-source')
  },
  stopDragging () {
    if (this.roomColumn) {
      this.roomColumn.classList.remove('hover-active')
      this.dragSource.classList.remove('drag-source')
      this.draggedTalk = null
      this.event = null
    }
  }
}

Vue.component('availability', {
  template: `
    <div class="room-availability" v-bind:style="style"></div>
  `,
  props: {
    availability: Object,
    start: Object,
  },
  computed: {
    duration () {
      if(this.availability.end) {
        return moment(this.availability.end).diff(this.availability.start, 'minutes')
      } else {
        return 60 * 24
      }
    },
    style () {
      var style = {height: this.duration + 'px'}
      style.transform = 'translatey(' + moment(this.availability.start).diff(this.start, 'minutes') + 'px)'
      return style
    },
  }
})

Vue.component('talk', {
  template: `
    <div class="talk-box" :class="[talk.state, {dragged: isDragged}]" v-bind:style="style" @mousedown="onMouseDown"
         :title="title">
      <span class="time" v-if="this.talk.start">
        {{ humanStart }}
      </span>
      {{ talk.title }} ({{ talk.duration }} minutes)
    </div>
  `,
  props: {
    talk: Object,
    start: Object,
    isDragged: {type: Boolean, default: false},
  },
  computed: {
    title () {
      return this.talk.title + ' (' + this.talk.duration + ' minutes)';
    },
    style () {
      var style = {height: this.talk.duration + 'px'}
      if (this.isDragged) {
        var rect = this.$parent.$el.getBoundingClientRect()

        var colRect
        if (dragController.roomColumn) {
          colRect = dragController.roomColumn.getBoundingClientRect()
        } else {
          colRect = app.$refs.unassigned.getBoundingClientRect()
        }
        var dragTop = Math.max(colRect.top, dragController.event.clientY - dragController.dragPosY) - rect.top
        var dragLeft = dragController.event.clientX - rect.left - dragController.dragPosX

        style.transform = 'translate(' + dragLeft + 'px,' + dragTop + 'px)'
        style.width = colRect.width + 'px'
      } else if (this.talk.room !== null) {
        style.transform = 'translatey(' + moment(this.talk.start).diff(this.start, 'minutes') + 'px)'
      }
      return style
    },
    humanStart () {
      return moment.tz(this.talk.start, app.timezone).format('HH:mm')
    }

  },
  methods: {
    onMouseDown (event) {
      if (event.buttons === 1) {
        var talkRect = this.$el.getBoundingClientRect()
        dragController.startDragging(this.talk, this.$el, event.clientX - talkRect.left, event.clientY - talkRect.top)
      }
    },
  }
})

Vue.component('timestep', {
  template: `
    <div class="timestep-box" v-bind:style="style" :class="[{midnight: isMidnight}]">
      {{ isMidnight ? timestep.format("MM-DD") : timestep.format("HH:mm") }}
    </div>
  `,
  props: {
    timestep: Object,
    start: Object,
  },
  computed: {
    style () {
      var style = {height: '30px'}
      style.transform = 'translatey(' + moment(this.timestep).diff(this.start, 'minutes') + 'px)'
      return style
    },
    isMidnight () {
      return (this.timestep.hour() === 0 && this.timestep.minute() === 0);
    }
  },
})

Vue.component('room', {
  template: `
    <div class="room-column">
      <div class="room-header"><a v-bind:href="room.url">{{ room.name }}</a></div>
      <div class="room-container" v-bind:style="style" :data-id="room.id">
      <availability v-for="avail in availabilities" :availability="avail" :start="start" :key="avail.id"></availability>
      <talk v-for="talk in myTalks" :talk="talk" :start="start" :key="talk.id"></talk>
      </div>
    </div>
  `,
  props: {
    talks: Array,
    room: Object,
    duration: Number,
    start: Object,
  },
  asyncComputed: {
    availabilities () {
      if (dragController.draggedTalk) {
        return api.fetchAvailabilities(
          dragController.draggedTalk.id,
          this.room.id,
        ).then(result => result.results);
      } else {
        return this.room.availabilities;
      }
    },
  },
  computed: {
    myTalks () {
      return (this.talks || []).filter((element) =>
        element.room === this.room.id
      )
    },
    style () {
      return {
        height: this.duration + 'px'
      }
    }
  }
})

var app = new Vue({
  el: '#fahrplan',
  template: `
    <div @mousemove="onMouseMove" @mouseup="onMouseUp">
      <div id="fahrplan">
        <talk ref="draggedTalk" v-if="dragController.draggedTalk && dragController.event" :talk="dragController.draggedTalk" :key="dragController.draggedTalk.id" :is-dragged="true"></talk>
        <div id="timeline">
          <div class="room-container">
            <timestep v-for="timestep in timesteps" :timestep="timestep" :start="start">
            </timestep>
          </div>
        </div>
        <div id="tracks">
          <div class="alert alert-danger room-column" v-if="rooms && rooms.length < 1">
            Please configure some rooms first.
          </div>
          <room v-for="room in rooms" :room="room" :talks="talks" :duration="duration" :start="start" :key="room.id">
          </room>
        </div>
      </div>
      <div id='unassigned-talks'>
        <div class="room-header" ref="roomHeader">Unassigned Talks</div>
        <div class="input-group">
          <div class="input-group-prepend input-group-text"><i class="fa fa-search"></i></div>
          <input type="text" class="form-control" placeholder="Search..." v-model="search">
        </div>
        <div class="room-container" id="unassigned-container" ref="unassigned">
            <talk v-for="talk in filteredTalks" v-if="!talk.room" :talk="talk" :key="talk.id"></talk>
        </div>
      </div>
    </div>
  `,
  data () {
    return {
      talks: null,
      rooms: null,
      start: null,
      end: null,
      timezone: null,
      search: '',
      dragController: dragController,
    }
  },
  created () {
    api.fetchTalks().then((result) => {
      this.talks = result.results
    })
    api.fetchRooms().then((result) => {
      this.rooms = result.rooms
      this.timezone = result.timezone
      this.start = moment.tz(result.start, this.timezone)
      this.end = moment.tz(result.end, this.timezone)
    })
  },
  computed: {
    currentDay () {
    },
    duration () {
      return this.end.diff(this.start, 'minutes')
    },
    timesteps () {
      var steps = [],
          d = moment(this.start);

      while (d < this.end) {
        steps.push(moment(d));
        d.add(30, 'm');
      }
      return steps;
    },
    filteredTalks() {
      if (!this.talks)
        return []
      return this.talks.filter(talk => {
         return talk.title.toLowerCase().indexOf(this.search.toLowerCase()) > -1
      })
    }
  },
  methods: {
    onMouseMove (event) {
      if (dragController.draggedTalk) {
        dragController.event = event
        var newRoomColumn = document.elementFromPoint(event.clientX, event.clientY)

        while (!newRoomColumn.className.match(/room-container/) && newRoomColumn.id !== "unassigned-container" && newRoomColumn.parentElement) {
          newRoomColumn = newRoomColumn.parentElement
        }

        if (newRoomColumn.dataset.id) {
          if (newRoomColumn && (newRoomColumn !== dragController.roomColumn)) {
            if (dragController.roomColumn)
              dragController.roomColumn.classList.remove('hover-active')
          }
          dragController.roomColumn = newRoomColumn
          dragController.draggedTalk.room = newRoomColumn.dataset.id
          dragController.roomColumn.classList.add('hover-active')
          if (dragController.roomColumn && app.$refs.draggedTalk) {
            var colRect = dragController.roomColumn.getBoundingClientRect()
            var dragRect = app.$refs.draggedTalk.$el.getBoundingClientRect()
            var position = dragRect.top - colRect.top
            position -= position % 5
            dragController.draggedTalk.start = moment(this.start).add(position, 'minutes').format()
          }
        } else if (newRoomColumn.id === "unassigned-container") {
          if (newRoomColumn && (newRoomColumn !== dragController.roomColumn)) {
            if (dragController.roomColumn)
              dragController.roomColumn.classList.remove('hover-active')
          }
          dragController.roomColumn = newRoomColumn
          dragController.draggedTalk.room = null
          dragController.draggedTalk.start = null
          dragController.roomColumn.classList.add('hover-active')
        }
      }
    },
    onMouseUp (event) {
      if (dragController.draggedTalk) {
        if (dragController.event) {
          api.saveTalk(dragController.draggedTalk).then((response) => {
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
    }
  }
})
