package com.iamsanaur.idt.ui

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.path
import androidx.compose.ui.unit.dp

/** Stroke icons matching the web app (24px grid). */
object IdtIcons {
    private fun stroke(name: String, block: androidx.compose.ui.graphics.vector.PathBuilder.() -> Unit) =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).path(
            fill = null, stroke = SolidColor(Color.Black), strokeLineWidth = 1.8f,
            strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round, pathBuilder = block,
        ).build()

    val Markets = stroke("markets") {
        moveTo(4f, 19f); lineTo(4f, 5f)
        moveTo(4f, 19f); lineTo(20f, 19f)
        moveTo(7f, 15f); lineTo(11f, 11f); lineTo(14f, 14f); lineTo(19f, 8f)
    }

    val Options = stroke("options") {
        moveTo(7f, 4f); lineTo(17f, 4f); quadTo(20f, 4f, 20f, 7f); lineTo(20f, 17f); quadTo(20f, 20f, 17f, 20f)
        lineTo(7f, 20f); quadTo(4f, 20f, 4f, 17f); lineTo(4f, 7f); quadTo(4f, 4f, 7f, 4f); close()
        moveTo(4f, 10f); lineTo(20f, 10f)
        moveTo(10f, 4f); lineTo(10f, 20f)
    }
}
