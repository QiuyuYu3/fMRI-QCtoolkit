library(shiny)
library(bslib)
library(DT)
library(plotly)
library(dplyr)
library(stringr)
library(tidyverse)
library(ggplot2)
library(jsonlite)
library(purrr)

# read file ---------------------------------------------------------------

session <- "01"
prefix <- "sub-"
project <- "branch"
task <- "kidvid_output"

based_dir <- "/work/cglab/projects/BRANCH/all_data/for_AFNI/BIDS"
output_dir <- "/scratch/qy49547/qc"

work_dir <- file.path(based_dir, project, "AFNI_derivatives")

# create a list for check box (from APQC web/qualitative data) and quantitative variables
rating_bases <- c("vorig", "ve2a", "va2t", "vstat", "mot", "regr", "radcor", "warns", "qsumm", "FINAL")
core_cols <- c("ID", "runs", "TRs_total_raw", "TRs_removed", "cens_mot", "cens_displace", "DF_frac", "TSNR", "cens_frac", "GCOR")

if (!dir.exists(work_dir)) stop(paste(work_dir, "does not exist"))

folders <- list.dirs(work_dir, full.names = TRUE, recursive = FALSE) %>%
  keep(~ grepl(paste0("^", prefix, "\\d{3}$"), basename(.)))

clean_key <- function(key) {
  key %>%
    str_replace_all("\\s+", "_") %>%
    str_replace_all("[()]", "")
}

all_data <- list()

for (folder in folders) {
  ID <- basename(folder)
  json_path <- file.path(folder, paste0("ses-", session), task, paste0(ID, ".results"),
                         paste0("QC_", ID), "extra_info", paste0("out.ss_review.", ID, ".json"))
  if (file.exists(json_path)) {
    tryCatch({
      data <- fromJSON(json_path)
      flat_data <- list(ID = ID)
      
      for (key in names(data)) {
        clean <- clean_key(key)
        val <- data[[key]]
        
        if (!is.null(val)) {
          if (length(val) == 1 && !is.list(val)) {
            flat_data[[clean]] <- val
          } else {
            for (i in seq_along(val)) {
              flat_data[[paste0(clean, "_", i)]] <- val[[i]]
            }
          }
        }
      }
      
      all_data <- append(all_data, list(flat_data))
    }, error = function(e) {
      message("Error reading ", json_path, ": ", e$message)
    })
  }
}

df <- bind_rows(all_data)

flip_convert <- function(val) {
  if (val == "NO_FLIP") return(0)
  if (!is.na(val)) return(1)
  return(NA)
}

df$flip_guess <- sapply(df$flip_guess, flip_convert)

rename_dict <- list(
  runs = "num_runs_found",
  TRs_total_raw = "TRs_total_uncensored",
  TRs_removed = "TRs_removed_per_run",
  cens_mot = "average_censored_motion",
  cens_displace = "max_censored_displacement",
  DF_frac = "final_DF_fraction",
  TSNR = "TSNR_average",
  cens_frac = "censor_fraction",
  GCOR = "global_correlation_GCOR"
)

for (i in 1:98) {
  rename_dict[[paste0("frac_TRs_cens_", i)]] <- paste0("fraction_TRs_censored_", i)
}

for (col in rating_bases) {
  rename_dict[[paste0(col, "_r")]] <- paste0(col, "_rating")
}

rename_dict_filtered <- rename_dict[sapply(rename_dict, function(old_name) old_name %in% names(df))]

df <- df %>% rename(!!!rename_dict_filtered)

frac_cols <- names(df)[grepl("^frac_TRs_cens_", names(df))]
checkbox_groups <- paste0(rating_bases, "_r")
vars <- c("cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "flip_guess", "GCOR", frac_cols)

df$ID <- str_replace(df$ID, paste0("^", prefix), "")

df_final <- df_final[, c(core_cols, frac_cols, checkbox_groups)]
df_final <- df %>% arrange(as.integer(ID))

write_csv(df_final, file.path(output_dir, "df_final.csv"))

for (col in setdiff(names(df_final), checkbox_groups)) {
  df_final[[col]] <- round(as.numeric(df_final[[col]]), 3)
}

quan_data <- df_final[, !(names(df_final) %in% checkbox_groups)]
vars_of_interest <- c("cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "GCOR", "TRs_total_raw")

mean_values <- colMeans(quan_data[, vars_of_interest], na.rm = TRUE)

scaled_data <- quan_data
scaled_data[, vars_of_interest] <- scale(quan_data[, vars_of_interest])

lollipop_chart_data <- pivot_longer(scaled_data, cols = all_of(vars_of_interest),
                                    names_to = "Variable", values_to = "Value") %>%
  mutate(
    mean_value = mean_values[Variable],
    subject_variable = paste0(ID, "_", Variable),
    Value = round(Value, 3),
    mean_value = round(mean_value, 3),
    ID_int = as.integer(ID)
  ) %>%
  arrange(Variable, ID_int) %>%
  mutate(row_number = row_number())


# function to assign status value to the plots
assign_status <- function(value, variable_name) {
  if (is.na(value)) return("NA")
  
  variable_name <- as.character(variable_name)[1] 
  
  result <- switch(variable_name,
                   "DF_frac" = {
                     if (value > 0.7) "good"
                     else if (value > 0.6) "other"
                     else "bad"
                   },
                   "cens_frac" = {
                     if (value >= 0.2) "bad"
                     else if (value >= 0.15) "other"
                     else "good"
                   },
                   "cens_mot" = {
                     if (value >= 0.15) "bad"
                     else if (value >= 0.1) "other"
                     else "good"
                   },
                   "cens_displace" = {
                     if (value >= 8) "bad"
                     else if (value >= 6) "other"
                     else "good"
                   },
                   "GCOR" = {
                     if (value >= 0.2) "bad"
                     else if (value >= 0.15) "other"
                     else "good"
                   },
                   "flip_guess" = {
                     if (value == 0) "good"
                     else "bad"
                   },
                   "TSNR" = {
                     if (value <= 150) "other"
                     else "good"
                   },
                   "other" 
  )
  
  return(result)
}

# Lollipop chart ----------------------------------------------------------

pp <- ggplot(lollipop_chart_data, aes(x = row_number, y = Value, color = Variable, group = Variable)) +
  geom_point(aes(shape = Variable, 
                 text = paste("ID: ", ID, "<br>Value: ", Value, "<br>Variable: ", Variable, "<br>Mean: ", mean_value)), 
             size = 3, position = position_jitter(width = 0.15), show.legend = TRUE)+
  geom_segment(aes(xend = row_number, yend = 0), linewidth = 0.5) +
  scale_color_brewer(palette = "Paired") +  
  labs(x = "Variables", y = "Standardized Value") +
  theme_minimal() +
  theme(axis.text.x = element_blank(),  
        axis.ticks.x = element_blank())  +  
  scale_shape_manual(values = rep(16, length(unique(lollipop_chart_data$ID))))

# use plotly to make it interactive
interactive_plot <- ggplotly(pp, tooltip = "text") %>%
  layout(
    hoverlabel = list(
      bgcolor = "dimgray",  
      font = list(color = "white")  
    ),
    clickmode = "event+select",  
    xaxis = list(
      rangeslider = list(type = "linear"),  
      showgrid = TRUE
    )
  ) 

# set up UIs --------------------------------------------------------------

# the sidebar will not show up if the range is set incorrectly.
ui <- fluidPage(
  fluidRow(
    column(2, 
           wellPanel(
             h3("Filters"),
             
             # a small note for filter
             helpText(
               "Final DF fraction > 0.7, Censor fraction < 0.15, Average censored motion < 0.1
               Max censored displacement < 6, Global correlation (GCOR) < 0.15, Flip guess,
               TSNR > 150(resting state), fraction TRs censored < 0.2"
             ),
             
             # now start to set the sidebar. I give a default value for every sidebar
             # you can change the value, step, and max value (I don't recommend to change them)
             # Just in case you want NA values, I create a checkbox to include NA
             sliderInput("cens_frac_table", "Censor Fraction", 
                         min = 0, 
                         max = max(df_final$cens_frac, na.rm = TRUE), 
                         value = c(0, 0.15),
                         step = 0.01),
             checkboxInput("cens_frac_include_na", "Include NA", value = T),  
             
             sliderInput("cens_mot_table", "Average Censored Motion", 
                         min = 0, 
                         max = max(df_final$cens_mot, na.rm = TRUE), 
                         value = c(0, 0.1),
                         step = 0.01),
             checkboxInput("cens_mot_include_na", "Include NA", value = T),  
             
             sliderInput("cens_displace_table", "Max Censored Displacement", 
                         min = 0, 
                         max = max(df_final$cens_displace, na.rm = TRUE)+20,
                         value = c(0, 6),
                         step = 0.01),
             checkboxInput("cens_displace_include_na", "Include NA", value = T),  
             
             sliderInput("TSNR_table", "TSNR Average", 
                         min = 0, 
                         max = max(df_final$TSNR, na.rm = TRUE)+1, 
                         value = c(min(df_final$TSNR, na.rm = TRUE)-1, max(df_final$TSNR, na.rm = T)+1), 
                         step = 1),
             checkboxInput("TSNR_include_na", "Include NA", value = T),
             
             sliderInput("DF_frac_table", "final DF fraction", 
                         min = 0, 
                         max = 1,
                         value = c(0.7, 1),
                         step = 0.1),
             checkboxInput("DF_frac_include_na", "Include NA", value = T),  
             
             sliderInput("flip_guess_table", "flip guess", 
                         min = 0, 
                         max = 1,
                         value = c(0, 1),
                         step = 1),
             checkboxInput("flip_guess_include_na", "Include NA", value = T),  
             
             sliderInput("GCOR_table", "GCOR", 
                         min = 0, 
                         max = 1,
                         value = c(0, 0.15)),
             checkboxInput("GCOR_include_na", "Include NA", value = T),  
             

            map(frac_cols, ~ tagList(
                sliderInput(
                inputId = paste0(.x, "_table"),
                label = .x,
                min = 0,
                max = 1,
                value = c(0, 0.2)
                ),
                checkboxInput(
                inputId = paste0(.x, "_include_na"),
                label = "Include NA",
                value = TRUE
                )
            )),
             
             # create the check box groups
             lapply(checkbox_groups, function(group) {
               selectizeInput(
                 inputId = group, 
                 label = group, 
                 choices = c("good", "other", "bad", "NA"), 
                 selected = c("good", "other", "bad", "NA"), 
                 multiple = TRUE,
                 options = list(plugins = list("remove_button")) 
               )
             })
             
           )
    ),
    
    # resize the panel
    column(10, 
           tabsetPanel(
             tabPanel("Table", 
                      DTOutput("datatable", height = "500px"),
                      fluidRow(
                        column(12, 
                               wellPanel(
                                 h4("Selected Row"),
                                 tableOutput("selected_row"),
                                 style = "overflow-y: auto; max-height: 400px; border: 1px solid #ddd;"
                               )
                        )
                      ),
                      fluidRow(
                        column(12, align = "right", 
                               downloadButton("downloadData", "Download Selected Data")
                        )
                      )
             ),
             
             # visualization
             tabPanel("Plots", 
                      fluidRow(
                        column(12, 
                               wellPanel(
                                 h4("Heatmap"),
                                 # Add tabset panel for different heatmaps
                                 tabsetPanel(
                                   tabPanel("Quantitative", 
                                            plotlyOutput("heatmap", height = "500px")),
                                   tabPanel("Qualitative", 
                                            plotlyOutput("qualitative_heatmap", height = "500px"))
                                 )
                               )
                        ),
                        column(12, 
                               wellPanel(
                                 h4("Lollipop Chart"),
                                 plotlyOutput("lollipop_chart", height = "600px")
                               )
                        )
                      )
             ),
             # resource page
             tabPanel("Resources", 
                      fluidRow(
                        column(12, 
                               wellPanel(
                                 h4("Reference"),
                                 p(a("https://afni.github.io/qc-demo-repo/", href = "https://afni.github.io/qc-demo-repo/")),
                                 
                                 p(a("Reynolds, R. C., Taylor, P. A., & Glen, D. R. (2023). Quality control practices in FMRI analysis: Philosophy, methods and examples using AFNI. Frontiers in Neuroscience, 16, 1073800. https://doi.org/10.3389/fnins.2022.1073800", 
                                     href = "https://doi.org/10.3389/fnins.2022.1073800")),
                                 
                                 p(a("Paul A. Taylor, Daniel R. Glen, Gang Chen, Robert W. Cox, Taylor Hanayik, Chris Rorden, Dylan M. Nielson, Justin K. Rajendra, Richard C. Reynolds; A Set of FMRI Quality Control Tools in AFNI: Systematic, in-depth, and interactive QC with afni_proc.py and more. Imaging Neuroscience 2024; 2 1–39. doi: https://doi.org/10.1162/imag_a_00246", 
                                     href = "https://doi.org/10.1162/imag_a_00246"))
                               )
                        )
                      )
             )
           )
    )
  )
)

# set up server -----------------------------------------------------------

server <- function(input, output, session) {
  
  # create filter -----------------------------------------------------------
  
  # filtered_data will pass the range, or value, of the previous input into the plots, 
  # the download section, these will change simultaneously
  
  filtered_data <- reactive({
    
    # filter for quan    
    numeric_filters <- Map(function(var) {
      list(
        val = sym(var),
        range = input[[paste0(var, "_table")]],
        include_na = input[[paste0(var, "_include_na")]]
      )
    }, vars)
    
    result <- df_final
    
    for(filter in numeric_filters) {
      result <- result %>%
        filter((!!filter$val >= filter$range[1] & !!filter$val <= filter$range[2]) |
                 (filter$include_na & is.na(!!filter$val)))
    }
    
    # filter for qual
    for(var in checkbox_groups) {
      var_sym <- sym(var)
      result <- result %>%
        filter((!!var_sym %in% input[[var]]) | 
                 (is.na(!!var_sym) & "NA" %in% input[[var]]))
    }
    
    result
  })
  
  # table panel -------------------------------------------------------------
  
  output$datatable <- renderDT({
    datatable(
      filtered_data(),
      selection = "multiple",
      options = list(
        pageLength = 10,
        autoWidth = TRUE,
        scrollX = TRUE
      ),
      rownames = FALSE
    )
  })
  
  # selected row and download data panel ------------------------------------
  
  output$selected_row <- renderTable({
    selected_rows <- input$datatable_rows_selected
    if (length(selected_rows) > 0) {
      selected_data <- filtered_data()[selected_rows, ]
      return(selected_data)
    } else {
      return(data.frame("Message" = "No row selected."))
    }
  })
  
  
  output$downloadData <- downloadHandler(
    filename = function() {
      paste("MRI_QC_subj.csv")
    },
    content = function(file) {
      selected_rows <- input$datatable_rows_selected
      if (length(selected_rows) > 0) {
        selected_data <- filtered_data()[selected_rows, ]
        write.csv(selected_data, file, row.names = FALSE)
      } else {
        write.csv(data.frame("Message" = "No row selected."), file, row.names = FALSE)
      }
    }
  )
  
  # lollipop_chart panel ----------------------------------------------------
  output$lollipop_chart <- renderPlotly({
    interactive_plot
  })
  
  # prepare data for heatmaps ----------------------------------------------
  
  # quantitative data preparation
  quantitative_heatmap_data <- reactive({
    req(filtered_data())  
    
    # do some data clean first
    quan_heatmap_data <- filtered_data() %>%
      select(ID, all_of(vars)) %>%
      pivot_longer(cols = -ID, names_to = "Variables", values_to = "Value")
    
    # create label(hover_text) by using status
    result <- quan_heatmap_data %>%
      rowwise() %>%
      mutate(
        Status = assign_status(Value, Variables),
        hover_text = sprintf(
          "Subject: %s<br>Variable: %s<br>Value: %s<br>Status: %s",
          ID,
          Variables,
          ifelse(is.na(Value), "NA", sprintf("%.3f", Value)),
          Status
        )
      ) %>%
      ungroup()
  })
  
  # qualitative data preparation
  qualitative_heatmap_data <- reactive({
    req(filtered_data())
    
    # extract qualitative data
    qual_data <- filtered_data() %>%
      select(ID, all_of(checkbox_groups)) %>%
      pivot_longer(cols = -ID, names_to = "Variables", values_to = "Status")
    
    # create hover text
    qual_data <- qual_data %>%
      mutate(
        hover_text = sprintf(
          "Subject: %s<br>Metric: %s<br>Status: %s",
          ID,
          Variables,
          ifelse(is.na(Status), "NA", Status)
        )
      )
    
    qual_data
  })
  
  create_heatmap <- function(data, variable_labels, title = "", y_text_angle = 45, n) {
    status_colors <- c(
      "bad" = "#F8786E", 
      "other" = "#FFD966", 
      "good" = "#C5E0B3", 
      "NA" = "#D3D3D3"
    )
    
    unique_ids <- unique(data$ID)
    total_rows <- length(unique_ids)
    rows_per_plot <- ceiling(total_rows / n)
    plot_list <- list()
    
    for (i in 1:n) {
      start_idx <- (i - 1) * rows_per_plot + 1
      end_idx <- min(i * rows_per_plot, total_rows)
      plot_ids <- unique_ids[start_idx:end_idx]
      
      data_part <- data %>%
        filter(ID %in% plot_ids)
      
      data_part$ID <- factor(data_part$ID, levels = plot_ids)
      
      p <- ggplot(data_part, aes(x = ID, y = Variables, fill = Status, text = hover_text)) +
        geom_tile(color = "white", linewidth = 0.5) +
        scale_y_discrete(labels = variable_labels) +
        scale_fill_manual(values = status_colors, na.value = "#D3D3D3") +
        theme_minimal() +
        theme(
          axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
          axis.text.y = element_text(angle = y_text_angle, hjust = 1, size = 8),
          legend.position = "right",
          panel.grid = element_blank()
        )
      
      p_plotly <- ggplotly(p, tooltip = "text")
      
      if (i != 1) {
        for (j in seq_along(p_plotly$x$data)) {
          p_plotly$x$data[[j]]$showlegend <- FALSE
        }
      }
      
      plot_list[[i]] <- p_plotly
    }
    
    subplot(plot_list, nrows = n, shareX = FALSE, shareY = FALSE, margin = 0.03) %>%
      layout(
        title = title,
        plot_bgcolor = 'white',
        margin = list(t = 50, b = 50),
        hoverlabel = list(bgcolor = "dimgray", font = list(color = "white"))
      )
  }
  
  # render the quantitative heatmap
  output$heatmap <- renderPlotly({
    req(quantitative_heatmap_data())
    
    # variable labels for quantitative metrics
    quant_variable_labels <- c(
      "cens_frac" = "cens fraction",
      "cens_mot" = "cens motion",
      "cens_displace" = "cens displace",
      "DF_frac" = "DF fraction",
      "flip_guess" = "flip guess",
      "TSNR" = "TSNR"
    )
    
    create_heatmap(
      data = quantitative_heatmap_data(),
      variable_labels = quant_variable_labels,
      title = "Quantitative Metrics Heatmap",
      n = 2
    )
  })
  
  # Render the qualitative heatmap
  output$qualitative_heatmap <- renderPlotly({
    req(qualitative_heatmap_data())
    
    # variable labels for qualitative metrics
    qual_variable_labels <- c(
      "mot_r" = "motion",
      "radcor_r" = "correlation",
      "regr_r" = "regression",
      "va2t_r" = "anat to template",
      "ve2a_r" = "EPI to anat",
      "vorig_r" = "vorig",
      "vstat_r" = "vstat",
      "warns_r" = "warnings",
      "qsumm_r" = "quantitative",
      "FINAL_r" = "final"
    )
    
    create_heatmap(
      data = qualitative_heatmap_data(),
      variable_labels = qual_variable_labels,
      title = "Qualitative Metrics Heatmap",
      n = 2
    )
  })
}  

shinyApp(ui = ui, server = server)