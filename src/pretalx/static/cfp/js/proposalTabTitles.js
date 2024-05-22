const titleParts = document.title.split("::")

document.addEventListener("DOMContentLoaded", () => {
    const titleInput = document.getElementById("id_title").value
    if (titleInput !== "") {
        document.title = `${titleInput} :: ${titleParts[1]} :: ${titleParts[2]}`
    }
})

if (titleParts.length !== 3) {
    console.error(
        "Could not parse site title while adding proposal title change listener.",
    )
} else {
    document.getElementById("id_title").addEventListener("change", (event) => {
        const newTitle = event.target.value
        if (newTitle === "") {
            document.title = titleParts.join(" :: ")
        } else {
            document.title = `${newTitle} :: ${titleParts[1]} :: ${titleParts[2]}`
        }
    })
}
